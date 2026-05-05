import math
from datetime import datetime, timezone
import asyncpg

from typing import Optional

def compute_decayed_score(
    s_last: float,
    updated_at: datetime,
    half_life_days: float,
    *,
    now: Optional[datetime] = None,
) -> float:
    """
    Computes the decayed salience score using the Ebbinghaus forgetting curve.
    s(t) = s_last * exp(-lambda * delta_t_days)
    where lambda = ln(2) / half_life_days

    Pass ``now`` in tests for deterministic evaluation; production callers omit it.
    """
    if half_life_days <= 0:
        return s_last

    ref = now if now is not None else datetime.now(timezone.utc)
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
        
    delta_t = (ref - updated_at).total_seconds() / 86400.0
    
    # Handle edge case: negative time (updated_at in the future)
    if delta_t < 0:
        return s_last
        
    decay_constant = math.log(2) / half_life_days
    return s_last * math.exp(-decay_constant * delta_t)

def ranking_score(cosine_sim: float, salience: float, alpha: float) -> float:
    """
    Computes the final ranking score combining cosine similarity and salience.
    final_score = cosine_similarity * (alpha + (1 - alpha) * salience_score)
    """
    # Ensure values are within bounds
    cosine_sim = max(0.0, min(1.0, float(cosine_sim)))
    salience = max(0.0, min(1.0, float(salience)))
    alpha = max(0.0, min(1.0, float(alpha)))
    
    return cosine_sim * (alpha + (1.0 - alpha) * salience)

async def reinforce(conn: asyncpg.Connection, memory_id: str, agent_id: str, namespace_id: str, delta: float = 0.05) -> None:
    """
    Reinforces a memory's salience score on retrieval.
    s_new = min(1.0, s_current + reinforcement_delta)
    """
    await conn.execute(
        """
        INSERT INTO memory_salience (memory_id, agent_id, namespace_id, salience_score, updated_at, access_count)
        VALUES ($1::uuid, $2, $3::uuid, LEAST(1.0, 1.0 + $4::real), NOW(), 1)
        ON CONFLICT (memory_id, agent_id) DO UPDATE
            SET salience_score = LEAST(1.0, memory_salience.salience_score + $4::real),
                updated_at = NOW(),
                access_count = memory_salience.access_count + 1
        """,
        memory_id, agent_id, namespace_id, delta
    )

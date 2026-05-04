package launch

import (
	"context"
	"fmt"
	"log/slog"
)

func runMultiuser(ctx context.Context, n UserNotifier, log *slog.Logger, appRoot string, env []string) error {
	dsn := LookupEnv(env, "PG_DSN")
	if dsn == "" {
		msg := "Database connection string (PG_DSN) is missing from configuration."
		n.Error("TriMCP", msg)
		return fmt.Errorf("PG_DSN missing")
	}
	host, port, err := PostgresAddrFromDSN(dsn)
	if err != nil {
		n.Error("TriMCP", "Could not read the Postgres address from PG_DSN. Contact IT.")
		if log != nil {
			log.Warn("pg_dsn_parse_failed", "err", err)
		}
		return err
	}

	tcpCtx, cancel := context.WithTimeout(ctx, pgTCPTimeout)
	defer cancel()
	if err := CheckTCPConnectivity(tcpCtx, host, port); err != nil {
		n.Error("TriMCP", "Cannot reach office server. VPN connected?")
		if log != nil {
			log.Warn("postgres_tcp_failed", "host", host, "port", port, "err", err)
		}
		return fmt.Errorf("postgres tcp: %w", err)
	}

	// Azure AD UPN refresh when a cache hook exists is deferred to a later phase; TCP proves reachability first.
	if log != nil {
		log.Info("multiuser_tcp_ok")
	}

	return runMCPServer(ctx, n, appRoot, env, log)
}

version: '3.8'

services:  
  \# 1\. Working Memory (Current Data)  
  redis:  
    image: redis:7-alpine  
    container\_name: tri-stack-redis  
    ports:  
      \- "6379:6379"  
    volumes:  
      \- redis\_data:/data  
    restart: unless-stopped

  \# 2\. Semantic Index (What Data is Stored)  
  postgres:  
    image: ankane/pgvector:v0.5.1 \# PostgreSQL 15 with pgvector pre-installed  
    container\_name: tri-stack-postgres  
    environment:  
      POSTGRES\_USER: mcp\_user  
      POSTGRES\_PASSWORD: mcp\_password  
      POSTGRES\_DB: memory\_meta  
    ports:  
      \- "5432:5432"  
    volumes:  
      \- pg\_data:/var/lib/postgresql/data  
    restart: unless-stopped

  \# 3\. Episodic Archive (The Complete Data)  
  mongodb:  
    image: mongo:7.0  
    container\_name: tri-stack-mongo  
    ports:  
      \- "27017:27017"  
    volumes:  
      \- mongo\_data:/data/db  
    restart: unless-stopped

volumes:  
  redis\_data:  
  pg\_data:  
  mongo\_data:  

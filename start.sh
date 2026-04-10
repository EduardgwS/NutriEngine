#!/bin/bash

# Ativa o ambiente do python
source .venv/bin/activate

if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

cloudflared tunnel run --token "$CLOUDFLARED_TOKEN" > /dev/null 2>&1 &
CLOUDFLARED_PID=$!

# Inicia uvicorn (coiso lá pra coisar o servidor kk)
uvicorn main:app --host localhost --port 5000 --reload

# Mata o cloudflared junto com o programa, aí tudo fica certinho
kill $CLOUDFLARED_PID
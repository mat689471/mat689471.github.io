# Immagine snella e recente: nessun compilatore, nessun peso inutile.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Prima le dipendenze, poi il codice: cambiando una riga di Python non si
# riscarica mezzo mondo a ogni build.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Il database e i diari stanno qui. Su un host senza disco permanente si
# azzerano a ogni riavvio: per tenerli, monta un volume su questa cartella
# (vedi LEGGIMI.md, sezione «Mettere il sistema online»).
RUN mkdir -p /app/dati
VOLUME ["/app/dati"]

# Non gira da root: se qualcosa va storto, i danni restano piccoli.
RUN useradd --create-home --uid 10001 clinica && chown -R clinica:clinica /app
USER clinica

# Il provider decide la porta e la passa in PORT. In locale vale 8000.
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import os,urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8000'), timeout=4).status==200 else 1)"

# I SEGRETI NON STANNO QUI. Arrivano dalle variabili d'ambiente del provider:
#   ANTHROPIC_API_KEY            una sola, globale
#   HUBSPOT_TOKEN_<STUDIO>       una per ogni cliente, col nome scritto in clienti.json
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

depuis la racine du repo :
```
git switch main && git pull
cd backend && uv sync
cp .env.example .env    # puis remplacer JWT_SECRET par un vrai secret (commande en commentaire dans le fichier)
uv run uvicorn app.main:app --reload    # vérifier /health et /docs

```

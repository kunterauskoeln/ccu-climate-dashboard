# Dashboard (Frontend)

React 18 + TypeScript + Vite; ausgeliefert von nginx, das auch `/api` an das Backend weiterreicht.

```bash
npm ci                                            # Abhängigkeiten (exakt nach package-lock.json)
echo "VITE_API_URL=http://localhost:8000" > .env.local   # lokales Backend
npm start                                         # Entwicklungsserver, Port 3000
npm run lint                                      # ESLint
npx tsc --noEmit                                  # Typprüfung
npm run build                                     # Produktionsbau nach build/
```

Aufbau, Routen, Hooks und Themen: [docs/06-architektur.md](../docs/06-architektur.md#65-frontend-im-detail).
Entwicklungsablauf: [docs/09-entwicklung.md](../docs/09-entwicklung.md).

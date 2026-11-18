# Cancha México

Aplicación web para explorar instalaciones deportivas de México con Leaflet, datos reales de OpenStreetMap e INEGI/DENUE y una paleta otoñal. La cobertura depende de las fuentes; no es un censo exhaustivo.

## Funciones

- Mapa con agrupación de miles de marcadores.
- Filtros por estado, municipio, localidad, deporte, tipo y nombre.
- Ubicación manual por dirección, localidad o punto en el mapa; sin GPS ni ubicación por IP.
- Diez instalaciones más cercanas mediante Haversine y distancias en línea recta.
- Estadísticas por estado, municipio y deporte.
- SQLite persistente, importación por estado, descarga nacional INEGI y cancelación.

## Ejecutar localmente

Requisitos: **Python 3.10 o posterior**. No requiere paquetes Python adicionales ni npm. Internet es necesario para Leaflet, mosaicos, búsquedas y descargas. Se utiliza curl del sistema cuando está disponible; de lo contrario, urllib.

Desde la carpeta del proyecto:

```sh
# Primera vez: descargar la base oficial de INEGI.
python server.py --download-denue

# Iniciar la aplicación.
python server.py
```

Abre [http://localhost:8000](http://localhost:8000). Si la descarga falla, inicia el servidor y reintenta desde **Datos abiertos y cobertura**. Para detenerlo, usa `Ctrl+C`.

**La base no se incluye en Git.** Se crea automáticamente en `data/`. Las copias locales existentes se conservan. Para cambiar el puerto: `python server.py --port 8080`.

## Importar datos

```sh
python server.py --download-denue        # INEGI nacional, independiente de Overpass
python server.py --denue "ruta/denue.csv"
python server.py --denue "ruta/denue_00_71_csv.zip"
python server.py --state JAL             # OSM: Jalisco
python server.py --state JAL --force     # OSM: actualizar Jalisco
python server.py --import-all            # OSM: 32 estados, reanudable
python server.py --bulk                  # OSM: consulta nacional, más exigente
```

Evita varios importadores simultáneos. Los estados OSM completados se omiten salvo con `--force`. Si ambos servidores Overpass fallan, la importación nacional se detiene y conserva la base. Con curl, el tiempo máximo de conexión es 8 segundos y el de descarga Overpass es 80 segundos por servidor.

Variables de entorno opcionales:

| Variable | Uso |
| --- | --- |
| `OVERPASS_URL` | URL completa del endpoint `/api/interpreter` preferido. |
| `GEOCODER_URL` | URL de una API compatible con Photon, terminada en `/api/`. |

## Fuentes y alcance

- [OpenStreetMap](https://www.openstreetmap.org/copyright), bajo ODbL, mediante [Overpass](https://overpass-api.de/) y [Private.coffee](https://overpass.private.coffee/). Se consultan etiquetas `leisure`/`sport`, incluidas instalaciones pequeñas y sin nombre. Los centros de polígonos no son necesariamente accesos.
- [INEGI/DENUE](https://www.inegi.org.mx/app/descarga/?ti=6), mediante el [ZIP nacional del sector 71](https://www.inegi.org.mx/contenidos/masiva/denue/denue_00_71_csv.zip), sujeto a los [Términos de Libre Uso de INEGI](https://www.inegi.org.mx/inegi/terminos.html). Se seleccionan clases 713941–713944, 713991–713992, 713910 y 713950: clubes, gimnasios, billar, ligas, golf y boliche. Son establecimientos económicos, no un inventario de todas las canchas comunitarias.
- [Photon](https://photon.komoot.io/), basado en OSM, para búsquedas manuales con caché y límite aproximado de una solicitud por segundo. La dirección escrita se envía al proveedor al buscar.

La carga local del 18 de noviembre de 2026 con DENUE 05/2026 (corregido el 1 de julio) produjo **37,599 registros en 32 estados y 1,718 municipios**. Es una referencia de esa descarga, no una cantidad garantizada en versiones futuras.

Los campos ausentes se muestran como «sin dato». En DENUE se asigna deporte sólo cuando la clase lo especifica. La cercanía considera todos los registros filtrados, no sólo los visibles. Verifica horarios y acceso con cada instalación.

Las IDs estables evitan duplicados al reimportar. En DENUE también se omiten coincidencias de nombre normalizado a unos 30 metros. Se conservan canchas distintas de un mismo complejo; pueden persistir duplicados cartográficos con IDs diferentes.

## Estructura

```text
server.py          Servidor local, API e importadores
public/            HTML, CSS, Leaflet y lógica de interfaz
tests/             Pruebas Python y JavaScript
data/              Base, descargas y caché locales, excluidas de Git
.github/workflows/ Verificaciones automáticas
```

## Verificación

Las pruebas JavaScript requieren **Node.js 22 o posterior**; no es necesario para ejecutar la aplicación.

```sh
python -m unittest discover -s tests
node --test tests/core.test.cjs
node --check public/app.js
```

GitHub Actions ejecuta estas comprobaciones en Windows y Linux. No abre navegadores ni realiza pruebas visuales. Las pruebas de red usan simulaciones, sin descargas reales.

## Subir a GitHub

Crea un repositorio vacío en GitHub, sin README inicial, y ejecuta desde esta carpeta:

```sh
git add .
git commit -m "Initial commit: Cancha Mexico"
git remote add origin https://github.com/TU_USUARIO/cancha-mexico.git
git push -u origin main
```

Sustituye `TU_USUARIO` por tu cuenta. Comprueba con `git status` que no se incluyan bases SQLite, ZIP, archivos `.env` ni cachés.

**GitHub almacena el código; GitHub Pages no ejecuta este servidor Python.** La aplicación está preparada para uso local en `127.0.0.1`. Publicarla como servicio requiere un entorno con Python y controles de acceso para las importaciones.

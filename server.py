"""Cancha México — Python 3.10+, sin dependencias externas."""
import argparse
from contextlib import contextmanager
import csv
import io
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)
STATES = dict(zip('AGU BCN BCS CAM CHP CHH CMX COA COL DUR GUA GRO HID JAL MEX MIC MOR NAY NLE OAX PUE QUE ROO SLP SIN SON TAB TAM TLA VER YUC ZAC'.split(), ['Aguascalientes','Baja California','Baja California Sur','Campeche','Chiapas','Chihuahua','Ciudad de México','Coahuila','Colima','Durango','Guanajuato','Guerrero','Hidalgo','Jalisco','Estado de México','Michoacán','Morelos','Nayarit','Nuevo León','Oaxaca','Puebla','Querétaro','Quintana Roo','San Luis Potosí','Sinaloa','Sonora','Tabasco','Tamaulipas','Tlaxcala','Veracruz','Yucatán','Zacatecas']))
LEISURE = 'pitch|stadium|sports_centre|sports_hall|swimming_pool|track|fitness_station|fitness_centre|golf_course|ice_rink|horse_riding'
job = {'running': False, 'message': 'Listo', 'errors': [], 'revision': 0}
job_lock = threading.Lock()
cancel_import = threading.Event()
geo_lock = threading.Lock()
geo_last = 0
DENUE_URL = 'https://www.inegi.org.mx/contenidos/masiva/denue/denue_00_71_csv.zip'
DENUE_CLASSES = {
    '713941': ('sports_centre', ''), '713942': ('sports_centre', ''),
    '713943': ('fitness_centre', 'fitness'), '713944': ('fitness_centre', 'fitness'),
    '713991': ('billiards_hall', 'billiards'), '713992': ('sports_club', ''),
    '713910': ('golf_course', 'golf'), '713950': ('bowling_alley', '10pin'),
}

class ImportCancelled(Exception):
    pass

class OverpassUnavailable(Exception):
    pass

@contextmanager
def db():
    c = sqlite3.connect(DATA / 'facilities.sqlite', timeout=60)
    c.row_factory = sqlite3.Row
    try:
        with c:
            yield c
    finally:
        c.close()

def initialize():
    with db() as c:
        c.executescript('''PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS facilities(id TEXT PRIMARY KEY,name TEXT,sport TEXT,type TEXT,state TEXT,municipality TEXT,city TEXT,lat REAL,lon REAL,address TEXT,access TEXT,source TEXT,url TEXT);
        CREATE INDEX IF NOT EXISTS state_idx ON facilities(state);
        CREATE INDEX IF NOT EXISTS lat_idx ON facilities(lat);
        CREATE TABLE IF NOT EXISTS imports(state TEXT PRIMARY KEY,updated TEXT,count INTEGER);
        CREATE TABLE IF NOT EXISTS geocache(q TEXT PRIMARY KEY,data TEXT);''')

def remote_bytes(url, data=None, timeout=80, cancellable=False):
    """Bound both connection and total time; curl uses the Windows TLS stack."""
    curl = shutil.which('curl.exe') or shutil.which('curl')
    if cancellable and cancel_import.is_set(): raise ImportCancelled()
    if curl:
        args = [curl, '-q', '--silent', '--show-error', '--fail', '--location',
                '--compressed', '--connect-timeout', '8', '--max-time', str(timeout),
                '--max-filesize', '104857600', '--user-agent', 'CanchaMexico/1.1', url]
        if data is not None: args += ['--data-binary', '@-']
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        deadline = time.monotonic() + timeout + 2
        first = True
        try:
            while True:
                if cancellable and cancel_import.is_set(): raise ImportCancelled()
                if time.monotonic() > deadline: raise TimeoutError('Tiempo de descarga agotado')
                try:
                    output, error = process.communicate(input=data if first else None, timeout=0.25)
                    break
                except subprocess.TimeoutExpired:
                    first = False
            if process.returncode:
                raise ConnectionError(error.decode('utf-8', errors='replace').strip())
            return output
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
    request = urllib.request.Request(url, data=data, headers={'User-Agent': 'CanchaMexico/1.0 (local sports atlas)', 'Accept': 'application/json'})
    deadline = time.monotonic() + timeout
    with urllib.request.urlopen(request, timeout=min(timeout, 12)) as response:
        chunks = []
        while True:
            if cancellable and cancel_import.is_set(): raise ImportCancelled()
            chunk = response.read1(1024 * 1024)
            if not chunk: break
            chunks.append(chunk)
            if time.monotonic() > deadline:
                raise TimeoutError('Tiempo de descarga agotado; reintenta por estado.')
        return b''.join(chunks)

def remote(url, data=None, timeout=80, cancellable=False):
    return json.loads(remote_bytes(url, data, timeout, cancellable))

def overpass(query):
    errors = []
    for endpoint in dict.fromkeys([os.getenv('OVERPASS_URL', 'https://overpass.private.coffee/api/interpreter'), 'https://overpass-api.de/api/interpreter']):
        try:
            job['message'] = 'Consultando ' + urllib.parse.urlparse(endpoint).hostname + '…'
            result = remote(endpoint + '?' + urllib.parse.urlencode({'data': query}), timeout=80, cancellable=True)
            if result.get('remark'):
                raise ValueError(result['remark'])
            return result['elements']
        except ImportCancelled:
            raise
        except Exception as exc:
            host = urllib.parse.urlparse(endpoint).hostname
            print(f'{host}: {exc}', flush=True)
            errors.append(host)
    raise OverpassUnavailable('No respondieron los servidores de OpenStreetMap (' + ', '.join(errors) + '). Usa la descarga INEGI o reintenta más tarde.')

def normalize(element, state):
    t = element.get('tags', {})
    p = element.get('center', element)
    if 'lat' not in p or 'lon' not in p:
        return None
    # Exclude shops, offices, clubs without mapped sports facilities and abandoned sites.
    if t.get('disused') == 'yes' or t.get('abandoned') == 'yes':
        return None
    return (f"osm:{element['type']}/{element['id']}", t.get('name', ''), t.get('sport', ''), t.get('leisure', 'sports_facility'), state,
            t.get('addr:municipality', t.get('addr:district', '')), t.get('addr:city', t.get('addr:town', t.get('addr:village', ''))),
            p['lat'], p['lon'], ' '.join(filter(None, [t.get('addr:street'), t.get('addr:housenumber'), t.get('addr:postcode')])),
            t.get('access', ''), 'OpenStreetMap', f"https://www.openstreetmap.org/{element['type']}/{element['id']}")

def save_elements(elements, state):
    rows = [row for e in elements if (row := normalize(e, state))]
    with db() as c:
        # Stable OSM IDs make refreshes idempotent; distinct courts in a complex remain distinct.
        c.executemany('INSERT OR REPLACE INTO facilities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', rows)
        c.execute('INSERT OR REPLACE INTO imports VALUES (?,?,?)', (state, time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), len(rows)))
    job['revision'] += 1
    return len(rows)

def import_state(code, force=False):
    state = STATES[code]
    with db() as c:
        if not force and c.execute('SELECT 1 FROM imports WHERE state=?', (state,)).fetchone():
            return
    job['message'] = f'Descargando {state}…'
    print(job['message'], flush=True)
    query = f'''[out:json][timeout:60];area["ISO3166-2"="MX-{code}"]->.a;
    (nwr(area.a)[leisure~"^({LEISURE})$"];nwr(area.a)[sport][leisure];);out center tags;'''
    elements = overpass(query)
    if cancel_import.is_set(): raise ImportCancelled()
    count = save_elements(elements, state)
    job['message'] = f'{state}: {count:,} instalaciones'
    print(job['message'], flush=True)

def import_national():
    # A single bulk request; emit each state area before its records to retain provenance.
    job['message'] = 'Descarga masiva de los 32 estados…'
    print(job['message'], flush=True)
    query = f'''[out:json][timeout:60];area["ISO3166-2"~"^MX-"][admin_level=4];
    foreach->.a(.a out tags;(nwr(area.a)[leisure~"^({LEISURE})$"];nwr(area.a)[sport][leisure];);out center tags;);'''
    elements = overpass(query)
    groups = {}
    state = None
    for e in elements:
        if e['type'] == 'area':
            code = e.get('tags', {}).get('ISO3166-2', '').removeprefix('MX-')
            state = STATES.get(code)
            if state: groups.setdefault(state, [])
        elif state:
            groups[state].append(e)
    if len(groups) != 32:
        raise ValueError(f'La descarga devolvió {len(groups)}/32 estados; use importación por estado.')
    for state, group in groups.items():
        print(f'{state}: {save_elements(group, state)}', flush=True)

def run_import(code, force=False, source='osm'):
    try:
        if source == 'denue':
            download_denue()
            return
        for key in ([code] if code != 'ALL' else STATES):
            if cancel_import.is_set(): raise ImportCancelled()
            try:
                import_state(key, force)
            except (OverpassUnavailable, ImportCancelled):
                raise
            except Exception as exc:
                job['errors'].append(f'{STATES[key]}: {exc}')
                print(job['errors'][-1], flush=True)
            if code == 'ALL' and cancel_import.wait(2): raise ImportCancelled()
        job['message'] = 'Importación finalizada' if not job['errors'] else 'Importación finalizada con errores; puedes reintentar.'
    except ImportCancelled:
        job['message'] = 'Importación cancelada. Se conservaron los datos ya guardados.'
    except Exception as exc:
        job['message'] = 'Descarga detenida. Se conservaron los datos existentes.'
        job['errors'].append(str(exc))
        print(str(exc), flush=True)
    finally:
        job['running'] = False

def fold(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.lower()) if not unicodedata.combining(c))

def import_denue(path, cancellable=False):
    # Official downloadable DENUE CSV: only sports facilities, not sporting goods stores.
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if n.startswith('conjunto_de_datos/') and n.lower().endswith('.csv')]
            if len(names) != 1: raise ValueError('El ZIP debe contener un CSV DENUE en conjunto_de_datos/.')
            if archive.getinfo(names[0]).file_size > 512 * 1024 * 1024: raise ValueError('CSV demasiado grande.')
            raw = archive.read(names[0])
    else:
        raw = Path(path).read_bytes()
    try: content = raw.decode('utf-8-sig')
    except UnicodeDecodeError: content = raw.decode('cp1252')
    reader = csv.DictReader(io.StringIO(content, newline=''), dialect=csv.Sniffer().sniff(content[:8192], delimiters=',;\t'))
    required = {'id','nom_estab','codigo_act','entidad','latitud','longitud'}
    if not required.issubset(reader.fieldnames or []): raise ValueError('El archivo no contiene las columnas requeridas del DENUE.')
    count = 0
    with db() as c:
        for original in reader:
            if cancellable and cancel_import.is_set(): raise ImportCancelled()
            r = {fold(k).strip(): (v or '').strip() for k, v in original.items() if k}
            activity = r.get('codigo_act', '')
            if activity not in DENUE_CLASSES: continue
            try: lat, lon = float(r['latitud']), float(r['longitud'])
            except (KeyError, ValueError): continue
            if not (14 <= lat <= 33.5 and -119 <= lon <= -86): continue
            ident = r.get('id', r.get('clee', ''))
            if not ident: continue
            name = r.get('nom_estab', '')
            # Cross-source near-identical named records: preserve the OSM record.
            nearby = c.execute('SELECT name FROM facilities WHERE id!=? AND lat BETWEEN ? AND ? AND ABS(lon-?)<0.0003', (f'denue:{ident}', lat-0.0003, lat+0.0003, lon))
            if name and any(fold(x['name']) == fold(name) for x in nearby): continue
            state = r.get('entidad', '')
            aliases = {'coahuila de zaragoza':'Coahuila','michoacan de ocampo':'Michoacán','veracruz de ignacio de la llave':'Veracruz','mexico':'Estado de México'}
            state = aliases.get(fold(state), next((v for v in STATES.values() if fold(v)==fold(state)), state))
            if state not in STATES.values(): continue
            facility_type, sport = DENUE_CLASSES[activity]
            c.execute('INSERT OR REPLACE INTO facilities VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', (f'denue:{ident}', name, sport, facility_type, state, r.get('municipio',''), r.get('localidad',''), lat, lon, ' '.join(filter(None,[r.get('nom_vial'),r.get('numero_ext')])), '', 'INEGI / DENUE', 'https://www.inegi.org.mx/app/mapa/denue/'))
            count += 1
    print(f'INEGI: {count} registros importados.')
    job['revision'] += 1
    return count

def download_denue():
    job['message'] = 'Descargando INEGI / DENUE nacional…'
    payload = remote_bytes(DENUE_URL, timeout=90, cancellable=True)
    if not zipfile.is_zipfile(io.BytesIO(payload)):
        raise ValueError('INEGI no devolvió un ZIP válido. La base existente no se modificó.')
    path = DATA / 'denue_00_71_csv.zip'
    path.write_bytes(payload)
    job['message'] = 'Importando establecimientos deportivos de INEGI…'
    count = import_denue(path, cancellable=True)
    job['message'] = f'INEGI: {count:,} registros importados. Puedes ampliar las canchas comunitarias con OSM cuando esté disponible.'

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'public'), **kwargs)

    def send_json(self, data, status=200):
        payload = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        try:
            if u.path == '/api/data':
                with db() as c:
                    rows = [dict(r) for r in c.execute('SELECT * FROM facilities')]
                    imports = [dict(r) for r in c.execute('SELECT * FROM imports')]
                return self.send_json({'facilities': rows, 'imports': imports, 'states': STATES})
            if u.path == '/api/status': return self.send_json(job)
            if u.path == '/api/geocode':
                term = q.get('q', [''])[0].strip()[:200]
                if len(term) < 3: return self.send_json({'error':'Escribe al menos 3 caracteres.'}, 400)
                global geo_last
                with geo_lock:
                    with db() as c:
                        cached = c.execute('SELECT data FROM geocache WHERE q=?', (term,)).fetchone()
                    if cached: return self.send_json(json.loads(cached['data']))
                    time.sleep(max(0, 1.1 - (time.monotonic() - geo_last)))
                    geo_last = time.monotonic()
                    params = urllib.parse.urlencode({'q':term, 'limit':8, 'bbox':'-118.5,14.3,-86.5,32.8'})
                    result = remote(os.getenv('GEOCODER_URL','https://photon.komoot.io/api/') + '?' + params, timeout=25)
                    items = [f for f in result.get('features',[]) if f.get('properties',{}).get('countrycode','').upper() == 'MX']
                    with db() as c: c.execute('INSERT OR REPLACE INTO geocache VALUES (?,?)', (term,json.dumps(items)))
                return self.send_json(items)
            if u.path.startswith('/api/'): return self.send_json({'error':'Ruta inexistente'},404)
            return super().do_GET()
        except Exception as exc:
            self.send_json({'error': str(exc)}, 502)

    def do_POST(self):
        if self.path not in ('/api/import', '/api/import/cancel'): return self.send_json({'error':'Ruta inexistente'},404)
        # Only same-origin local UI may start an expensive import.
        if self.headers.get('Origin') not in (None, 'http://' + self.headers.get('Host','')):
            return self.send_json({'error':'Origen no autorizado'},403)
        if self.path == '/api/import/cancel':
            with job_lock:
                if job['running']:
                    cancel_import.set()
                    job['message'] = 'Cancelando la descarga…'
            return self.send_json(job)
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size > 1024: return self.send_json({'error':'Solicitud demasiado grande'},413)
            payload = json.loads(self.rfile.read(size))
            code = payload.get('state','ALL')
            source = payload.get('source', 'osm')
            if source not in ('osm', 'denue'): return self.send_json({'error':'Fuente inválida'},400)
            if code not in STATES and code != 'ALL': return self.send_json({'error':'Estado inválido'},400)
            with job_lock:
                if job['running']: return self.send_json({'error':'Ya hay una importación activa'},409)
                cancel_import.clear()
                job.update(running=True, message='Iniciando…', errors=[])
                threading.Thread(target=run_import, args=(code, bool(payload.get('force')), source), daemon=True).start()
            self.send_json(job,202)
        except (ValueError, TypeError): self.send_json({'error':'Solicitud inválida'},400)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--import-all', action='store_true')
    parser.add_argument('--bulk', action='store_true')
    parser.add_argument('--state', choices=STATES)
    parser.add_argument('--force', action='store_true')
    parser.add_argument('--denue', help='Ruta a CSV oficial DENUE')
    parser.add_argument('--download-denue', action='store_true', help='Descarga e importa el sector 71 nacional de INEGI')
    args = parser.parse_args()
    initialize()
    if args.download_denue:
        run_import('ALL', source='denue')
        if job['errors']: raise SystemExit(1)
    elif args.denue: import_denue(args.denue)
    elif args.bulk: import_national()
    elif args.import_all or args.state:
        run_import(args.state or 'ALL', args.force)
        if job['errors']: raise SystemExit(1)
    else:
        print(f'Cancha México: http://localhost:{args.port}', flush=True)
        ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()

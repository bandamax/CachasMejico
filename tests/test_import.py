import tempfile
import unittest
from pathlib import Path
import sys
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server

class Imports(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = server.DATA
        server.DATA = Path(self.temp.name)
        server.initialize()

    def tearDown(self):
        server.DATA = self.old
        self.temp.cleanup()

    def test_idempotent_and_no_invented_metadata(self):
        element = {'type':'way','id':1,'center':{'lat':20.5,'lon':-100.5},'tags':{'leisure':'pitch'}}
        server.save_elements([element, element], 'Guanajuato')
        server.save_elements([element], 'Guanajuato')
        with server.db() as connection:
            rows = connection.execute('SELECT * FROM facilities').fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['name'], '')
            self.assertEqual(rows[0]['sport'], '')
            self.assertEqual(rows[0]['municipality'], '')

    def test_denue_sports_only_and_coordinates_required(self):
        path = server.DATA / 'denue.csv'
        path.write_text('id,nom_estab,codigo_act,entidad,municipio,localidad,latitud,longitud\n1,Centro,713943,Jalisco,Zapopan,Zapopan,20.7,-103.4\n2,Tienda,465215,Jalisco,Zapopan,Zapopan,20.7,-103.4\n3,Sin punto,713943,Jalisco,Zapopan,Zapopan,,\n', encoding='utf-8')
        server.import_denue(path)
        server.import_denue(path)
        with server.db() as connection:
            rows = connection.execute('SELECT * FROM facilities').fetchall()
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['id'],'denue:1')

    def test_missing_coordinates_are_not_fabricated(self):
        self.assertIsNone(server.normalize({'type':'way','id':2,'tags':{}},'Jalisco'))

    def test_official_zip_preserves_source_classification(self):
        path = server.DATA / 'denue.zip'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('conjunto_de_datos/denue_71.csv', 'id,nom_estab,codigo_act,entidad,municipio,localidad,latitud,longitud\n1,Boliche,713950,Jalisco,Zapopan,Zapopan,20.7,-103.4\n')
        self.assertEqual(server.import_denue(path), 1)
        with server.db() as connection:
            row = connection.execute('SELECT * FROM facilities').fetchone()
            self.assertEqual(row['type'], 'bowling_alley')
            self.assertEqual(row['sport'], '10pin')

if __name__ == '__main__': unittest.main()

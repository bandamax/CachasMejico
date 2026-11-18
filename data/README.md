# Datos locales

Esta carpeta contiene la base `facilities.sqlite`, sus archivos temporales y las descargas oficiales. Estos archivos no se incluyen en Git; tu copia local se conserva.

Desde la raíz del proyecto, carga datos reales con:

```sh
python server.py --download-denue
```

También puedes descargarlos desde la interfaz o importar un CSV/ZIP oficial:

```sh
python server.py --denue "ruta/al/denue_00_71_csv.zip"
```

La base incluye una caché de las búsquedas manuales de direcciones. No publiques esa base personal. Las condiciones de uso de los datos corresponden a [INEGI](https://www.inegi.org.mx/inegi/terminos.html) y [OpenStreetMap](https://www.openstreetmap.org/copyright), según la fuente.

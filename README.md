
# Análisis de Energía Eléctrica en Chile - Power BI

Este repositorio contiene el desarrollo de un modelo dimensional orientado al análisis del sistema eléctrico chileno. El proyecto utiliza datos públicos del Coordinador Eléctrico Nacional para construir una base de datos relacional en MySQL y posteriormente visualizar la información mediante Power BI.

El análisis se centra en tres procesos principales:

1. Generación eléctrica por tecnología.
2. Ventas de energía por tipo de cliente.
3. Capacidad instalada por tecnología y región.

El objetivo del proyecto es transformar archivos históricos en una estructura analítica basada en modelos estrella, permitiendo estudiar la evolución de la generación eléctrica, la participación de tecnologías renovables, el comportamiento de las ventas de energía y la distribución territorial de la capacidad instalada.

---

## Fuentes de datos

Los datos utilizados provienen del **Coordinador Eléctrico Nacional**, organismo que publica información estadística histórica relacionada con la operación del sistema eléctrico chileno.

Sitio principal:

```text
https://www.coordinador.cl/
````

Sección de reportes y estadísticas:

```text
https://www.coordinador.cl/reportes-y-estadisticas/
```

### Archivos utilizados

Los archivos descargados y utilizados en el proyecto son los siguientes:

| Archivo                                       | Descripción                                                  | Uso en el modelo                                                   |
| --------------------------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------------ |
| `CEN-hist_gen_de_energia_por_tecnologia.xlsx` | Histórico de generación de energía eléctrica por tecnología. | Construcción de `fact_generacion_electrica`.                       |
| `CEN-hist_ventas_de_energia.xlsx`             | Histórico de ventas de energía.                              | Construcción de `fact_ventas_energia`.                             |
| `CEN-hist_cap_inst_por_tecnologia.xlsx`       | Histórico de capacidad instalada por tecnología.             | Apoyo al análisis de capacidad instalada por sistema y tecnología. |
| `CEN-hist_cap_inst_por_region_y_tecno.xlsx`   | Histórico de capacidad instalada por región y tecnología.    | Construcción de `fact_capacidad_instalada`.                        |

### URLs directas de descarga

```text
https://www.coordinador.cl/wp-content/uploads/2026/05/CEN-hist_gen_de_energia_por_tecnologia.xlsx
```

```text
https://www.coordinador.cl/wp-content/uploads/2026/05/CEN-hist_ventas_de_energia.xlsx
```

```text
https://www.coordinador.cl/wp-content/uploads/2026/05/CEN-hist_cap_inst_por_tecnologia.xlsx
```

```text
https://www.coordinador.cl/wp-content/uploads/2026/05/CEN-hist_cap_inst_por_region_y_tecno.xlsx
```


## Scripts del proyecto

El proceso de carga se implementa mediante dos scripts principales ubicados en la carpeta `scripts/`.

## Requisitos

Para ejecutar el proyecto se requiere:

* Python 3.10 o superior.
* MySQL instalado y en ejecución.
* Archivos Excel descargados desde el Coordinador Eléctrico Nacional.
* Dependencias Python instaladas desde `requirements.txt`.
* Archivo `.env` configurado en la carpeta `scripts/`.

---

## Instalación de dependencias

Se recomienda crear un entorno virtual:

```bash
python -m venv venv
```

Activar el entorno virtual en Windows PowerShell:

```bash
.\venv\Scripts\Activate.ps1
```

Instalar dependencias:

```bash
pip install -r requirements.txt
```

---

## Configuración de variables de entorno

Los scripts utilizan un archivo `.env` dentro de la carpeta `scripts/`.

Ejemplo de configuración:

```env
DB_USER=root
DB_PASSWORD=tu_password
HOST_DB=localhost
PORT_DB=3306
DB_NAME=energia_chile_dw
```

El archivo `.env` no debe versionarse, ya que puede contener credenciales locales.

---

## Orden de ejecución

Desde la raíz del repositorio, ejecutar:

```bash
python scripts/create_star_models.py
```

Luego validar los archivos sin modificar la base de datos:

```bash
python scripts/populate_star_models.py --dry-run
```

Finalmente, cargar el modelo dimensional:

```bash
python scripts/populate_star_models.py
```

Para una ejecución desde cero, se puede usar:

```bash
python scripts/create_star_models.py --drop-existing
python scripts/populate_star_models.py
```

---

## Informe en Power BI

El archivo de Power BI se encuentra en la carpeta:

```text
powerbi/
```

Archivo:

```text
informe_energia_chile.pbix
```

El informe interactivo se conecta al modelo dimensional en MySQL y permite analizar:

* Evolución de la generación eléctrica.
* Participación de generación renovable y no renovable.
* Tecnologías con mayor generación eléctrica.
* Evolución de ventas de energía.
* Ventas por tipo de cliente.
* Capacidad instalada por región y tecnología.

---

## Respaldo de base de datos

El respaldo de la base de datos se encuentra en:

```text
backup/energia_chile_dw.sql
```

Para restaurarlo en MySQL:

```bash
mysql -u root -p energia_chile_dw < backup/energia_chile_dw.sql
```

---

## Herramientas utilizadas

* Python
* pandas
* SQLAlchemy
* PyMySQL
* MySQL
* Power BI Desktop
* PlantUML
* Coordinador Eléctrico Nacional como fuente pública de datos


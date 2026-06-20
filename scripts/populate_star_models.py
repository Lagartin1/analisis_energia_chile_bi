"""Lee los Excel del CEN, transforma sus datos y puebla el modelo estrella."""

from __future__ import annotations

import argparse
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from create_star_models import (
    DimDate,
    DimRegion,
    DimSistema,
    DimTecnologia,
    DimTipoCliente,
    FactCapacidadInstalada,
    FactGeneracionElectrica,
    FactVentasEnergia,
    create_star_schema,
)


PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_DIR / "data"

GENERATION_FILE = DATA_DIR / "CEN-hist_gen_de_energia_por_tecnologia.xlsx"
SALES_FILE = DATA_DIR / "CEN-hist_ventas_de_energia.xlsx"
CAPACITY_TECH_FILE = DATA_DIR / "CEN-hist_cap_inst_por_tecnologia.xlsx"
CAPACITY_REGION_FILE = DATA_DIR / "CEN-hist_cap_inst_por_region_y_tecno.xlsx"

MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

MONTH_NAMES = {
    1: "Enero",
    2: "Febrero",
    3: "Marzo",
    4: "Abril",
    5: "Mayo",
    6: "Junio",
    7: "Julio",
    8: "Agosto",
    9: "Septiembre",
    10: "Octubre",
    11: "Noviembre",
    12: "Diciembre",
}

SYSTEM_METADATA = {
    "Sistema Eléctrico Nacional": "Nacional consolidado",
    "SIC": "Sistema interconectado histórico",
    "SING": "Sistema interconectado histórico",
}

CLIENT_METADATA = {
    "Distribuidor": (
        "Regulado",
        "Energía vendida a empresas distribuidoras.",
    ),
    "Libre": (
        "No regulado",
        "Energía vendida a clientes libres.",
    ),
    "Total": (
        "Agregado",
        "Total sin desglose por tipo de cliente en la fuente.",
    ),
}

MEASURE_QUANTUM = Decimal("0.000001")
MAX_MEASURE = Decimal("99999999999999.999999")


@dataclass(frozen=True)
class GenerationRow:
    fecha: date
    sistema: str
    tecnologia: str
    energia_gwh: Decimal


@dataclass(frozen=True)
class SalesRow:
    fecha: date
    sistema: str
    tipo_cliente: str
    energia_gwh: Decimal


@dataclass(frozen=True)
class CapacityRow:
    fecha: date
    sistema: str
    tecnologia: str
    region: str
    nivel_geografico: str
    capacidad_mw: Decimal


def normalize_key(value: Any) -> str:
    text_value = unicodedata.normalize("NFKD", str(value).strip().lower())
    return "".join(char for char in text_value if not unicodedata.combining(char))


def parse_measure(value: Any) -> Decimal | None:
    """Convierte una medida a Decimal(20, 6); rechaza booleanos y no finitos."""
    if value is None or pd.isna(value):
        return None
    if isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite():
        return None
    return number.quantize(MEASURE_QUANTUM)


def measure_value(value: Any, field_name: str) -> Decimal:
    number = parse_measure(value)
    if number is None:
        raise ValueError(f"{field_name} no es un número decimal válido: {value!r}")
    if number < 0:
        raise ValueError(f"{field_name} no puede ser negativo: {number}")
    if number > MAX_MEASURE:
        raise ValueError(
            f"{field_name} excede la capacidad de DECIMAL(20, 6): {number}"
        )
    return number


def parse_year(value: Any) -> int | None:
    """Devuelve un int sólo si el valor representa un año entero válido."""
    if value is None or pd.isna(value) or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite() or number != number.to_integral_value():
        return None
    year = int(number)
    return year if 1900 <= year <= 2100 else None


def canonical_technology(value: Any) -> str:
    key = normalize_key(value).replace("*", "").strip()
    aliases = {
        "hidrico": "Hidráulica",
        "hidraulica": "Hidráulica",
        "hidroelectrica": "Hidráulica",
        "carbon": "Carbón",
        "diesel": "Diésel",
        "petroleo": "Diésel",
        "gas": "Gas Natural",
        "gas natural": "Gas Natural",
        "eolico": "Eólica",
        "eolica": "Eólica",
        "solar": "Solar",
        "termosolar": "Termosolar",
        "geotermico": "Geotérmica",
        "geotermica": "Geotérmica",
        "otros": "Otros térmicos",
        "otros termicos": "Otros térmicos",
        "fuel oil": "Fuel Oil",
        "petcoke": "Petcoke",
        "cogeneracion": "Cogeneración",
        "biogas": "Biogás",
        "biomasa": "Biomasa",
    }
    if key not in aliases:
        raise ValueError(f"Tecnología no reconocida: {value!r}")
    return aliases[key]


def technology_metadata(technology: str) -> tuple[str, str, bool]:
    metadata = {
        "Hidráulica": ("Renovable convencional", "Agua", True),
        "Eólica": ("Renovable no convencional", "Viento", True),
        "Solar": ("Renovable no convencional", "Sol", True),
        "Termosolar": ("Renovable no convencional", "Sol", True),
        "Geotérmica": ("Renovable no convencional", "Geotermia", True),
        "Biogás": ("Renovable no convencional", "Biogás", True),
        "Biomasa": ("Renovable no convencional", "Biomasa", True),
        "Carbón": ("Térmica fósil", "Carbón", False),
        "Diésel": ("Térmica fósil", "Derivado del petróleo", False),
        "Gas Natural": ("Térmica fósil", "Gas natural", False),
        "Fuel Oil": ("Térmica fósil", "Derivado del petróleo", False),
        "Petcoke": ("Térmica fósil", "Derivado del petróleo", False),
        "Cogeneración": ("Térmica", "Mixto", False),
        "Otros térmicos": ("Térmica", "Mixto", False),
    }
    return metadata[technology]


def region_zone(region: str) -> str:
    zones = {
        "Arica y Parinacota": "Norte",
        "Tarapacá": "Norte",
        "Antofagasta": "Norte",
        "Atacama": "Norte",
        "Coquimbo": "Norte Chico",
        "Valparaíso": "Centro",
        "Metropolitana": "Centro",
        "O'Higgins": "Centro",
        "Maule": "Centro Sur",
        "Ñuble": "Centro Sur",
        "Biobío": "Centro Sur",
        "La Araucanía": "Sur",
        "Los Ríos": "Sur",
        "Los Lagos": "Sur",
        "Todas las regiones": "Nacional",
    }
    return zones.get(region, "Sin clasificar")


def ensure_files_exist() -> None:
    required = [
        GENERATION_FILE,
        SALES_FILE,
        CAPACITY_TECH_FILE,
        CAPACITY_REGION_FILE,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("No se encontraron archivos requeridos:\n" + "\n".join(missing))


def extract_generation() -> list[GenerationRow]:
    raw = pd.read_excel(GENERATION_FILE, sheet_name=1, header=None)
    headers = raw.iloc[2]
    rows: list[GenerationRow] = []
    for _, source in raw.iloc[3:].iterrows():
        year = parse_year(source.iloc[1])
        if year is None:
            continue
        for column in range(2, 15):
            if parse_measure(source.iloc[column]) is None:
                continue
            rows.append(
                GenerationRow(
                    fecha=date(year, 12, 31),
                    sistema="Sistema Eléctrico Nacional",
                    tecnologia=canonical_technology(headers.iloc[column]),
                    energia_gwh=measure_value(
                        source.iloc[column], "energia_generada_gwh"
                    ),
                )
            )
    return rows


def _append_sales_breakdown(
    rows: list[SalesRow],
    source: pd.Series,
    fecha: date,
    sistema: str,
    distributor_column: int,
    free_column: int,
) -> bool:
    inserted = False
    for client_type, column in (
        ("Distribuidor", distributor_column),
        ("Libre", free_column),
    ):
        if parse_measure(source.iloc[column]) is not None:
            rows.append(
                SalesRow(
                    fecha=fecha,
                    sistema=sistema,
                    tipo_cliente=client_type,
                    energia_gwh=measure_value(
                        source.iloc[column], "energia_vendida_gwh"
                    ),
                )
            )
            inserted = True
    return inserted


def extract_sales() -> list[SalesRow]:
    raw = pd.read_excel(SALES_FILE, sheet_name=1, header=None)
    rows: list[SalesRow] = []
    current_year: int | None = None

    for _, source in raw.iloc[3:].iterrows():
        parsed_year = parse_year(source.iloc[1])
        if parsed_year is not None:
            current_year = parsed_year
        if current_year is None:
            continue

        month_key = normalize_key(source.iloc[2])
        if month_key not in MONTHS:
            continue
        fecha = date(current_year, MONTHS[month_key], 1)

        sic_has_detail = _append_sales_breakdown(rows, source, fecha, "SIC", 3, 4)
        if not sic_has_detail and parse_measure(source.iloc[5]) is not None:
            rows.append(
                SalesRow(
                    fecha=fecha,
                    sistema="SIC",
                    tipo_cliente="Total",
                    energia_gwh=measure_value(
                        source.iloc[5], "energia_vendida_gwh"
                    ),
                )
            )

        _append_sales_breakdown(rows, source, fecha, "SING", 6, 7)
        _append_sales_breakdown(
            rows,
            source,
            fecha,
            "Sistema Eléctrico Nacional",
            8,
            9,
        )

    return rows


def _extract_capacity_sheet(sheet_index: int, system: str) -> list[CapacityRow]:
    raw = pd.read_excel(CAPACITY_TECH_FILE, sheet_name=sheet_index, header=None)
    headers = raw.iloc[2]
    rows: list[CapacityRow] = []
    for _, source in raw.iloc[3:].iterrows():
        year = parse_year(source.iloc[1])
        if year is None:
            continue
        for column in range(2, 11):
            if parse_measure(source.iloc[column]) is None:
                continue
            rows.append(
                CapacityRow(
                    fecha=date(year, 12, 31),
                    sistema=system,
                    tecnologia=canonical_technology(headers.iloc[column]),
                    region="Todas las regiones",
                    nivel_geografico="SISTEMA",
                    capacidad_mw=measure_value(
                        source.iloc[column], "capacidad_instalada_mw"
                    ),
                )
            )
    return rows


def extract_capacity_by_technology() -> list[CapacityRow]:
    rows: list[CapacityRow] = []
    rows.extend(_extract_capacity_sheet(1, "Sistema Eléctrico Nacional"))
    rows.extend(_extract_capacity_sheet(2, "SIC"))
    rows.extend(_extract_capacity_sheet(3, "SING"))
    return rows


def extract_capacity_by_region() -> list[CapacityRow]:
    raw = pd.read_excel(CAPACITY_REGION_FILE, sheet_name=1, header=None)
    rows: list[CapacityRow] = []

    for base_column in (1, 13):
        header_rows = [
            index
            for index in raw.index
            if parse_year(raw.iloc[index, base_column]) is not None
        ]
        for position, header_index in enumerate(header_rows):
            year = parse_year(raw.iloc[header_index, base_column])
            if year is None:
                raise ValueError("Se detectó un encabezado anual inválido.")
            end_index = (
                header_rows[position + 1] if position + 1 < len(header_rows) else len(raw)
            )
            headers = raw.iloc[header_index]

            for row_index in range(header_index + 1, end_index):
                region_value = raw.iloc[row_index, base_column]
                if not isinstance(region_value, str):
                    continue
                region = region_value.strip()
                if normalize_key(region) == "total":
                    continue

                for column in range(base_column + 1, base_column + 10):
                    value = raw.iloc[row_index, column]
                    if parse_measure(value) is None:
                        continue
                    rows.append(
                        CapacityRow(
                            fecha=date(year, 12, 31),
                            sistema="Sistema Eléctrico Nacional",
                            tecnologia=canonical_technology(headers.iloc[column]),
                            region=region,
                            nivel_geografico="REGION",
                            capacidad_mw=measure_value(
                                value, "capacidad_instalada_mw"
                            ),
                        )
                    )
    return rows


def deduplicate(rows: Iterable[Any], key_fields: tuple[str, ...]) -> list[Any]:
    result: dict[tuple[Any, ...], Any] = {}
    for row in rows:
        key = tuple(getattr(row, field) for field in key_fields)
        result[key] = row
    return list(result.values())


def extract_all() -> tuple[list[GenerationRow], list[SalesRow], list[CapacityRow]]:
    ensure_files_exist()
    generation = deduplicate(
        extract_generation(),
        ("fecha", "sistema", "tecnologia"),
    )
    sales = deduplicate(
        extract_sales(),
        ("fecha", "sistema", "tipo_cliente"),
    )
    capacity = deduplicate(
        extract_capacity_by_technology() + extract_capacity_by_region(),
        ("fecha", "sistema", "tecnologia", "region"),
    )
    validate_extracted_types(generation, sales, capacity)
    return generation, sales, capacity


def validate_extracted_types(
    generation: list[GenerationRow],
    sales: list[SalesRow],
    capacity: list[CapacityRow],
) -> None:
    """Verifica los tipos que se enviarán a SQL antes de abrir una conexión."""
    all_rows = [*generation, *sales, *capacity]
    for row in all_rows:
        if type(row.fecha) is not date:
            raise TypeError(f"fecha debe ser date, recibido {type(row.fecha).__name__}")
        if not all(
            isinstance(value, str) and value.strip()
            for value in (
                row.sistema,
                getattr(row, "tecnologia", None)
                or getattr(row, "tipo_cliente", None),
            )
        ):
            raise TypeError(f"Dimensiones de texto inválidas en {row!r}")

    for row in generation:
        if type(row.energia_gwh) is not Decimal or row.energia_gwh < 0:
            raise TypeError(f"Generación inválida: {row!r}")
    for row in sales:
        if type(row.energia_gwh) is not Decimal or row.energia_gwh < 0:
            raise TypeError(f"Venta inválida: {row!r}")
    for row in capacity:
        if type(row.capacidad_mw) is not Decimal or row.capacidad_mw < 0:
            raise TypeError(f"Capacidad inválida: {row!r}")
        if row.nivel_geografico not in {"SISTEMA", "REGION"}:
            raise ValueError(f"Nivel geográfico inválido: {row.nivel_geografico}")


def _get_or_create(
    session: Session,
    model: type,
    lookup_field: str,
    lookup_value: Any,
    **values: Any,
) -> Any:
    column = getattr(model, lookup_field)
    instance = session.scalar(select(model).where(column == lookup_value))
    if instance is None:
        instance = model(**{lookup_field: lookup_value}, **values)
        session.add(instance)
        session.flush()
    else:
        for key, value in values.items():
            setattr(instance, key, value)
    return instance


def populate_database(
    generation: list[GenerationRow],
    sales: list[SalesRow],
    capacity: list[CapacityRow],
) -> None:
    engine = create_star_schema(echo=False)
    with Session(engine) as session, session.begin():
        session.execute(delete(FactGeneracionElectrica))
        session.execute(delete(FactVentasEnergia))
        session.execute(delete(FactCapacidadInstalada))

        all_dates = sorted(
            {row.fecha for row in generation}
            | {row.fecha for row in sales}
            | {row.fecha for row in capacity}
        )
        date_ids: dict[date, int] = {}
        for value in all_dates:
            dimension = _get_or_create(
                session,
                DimDate,
                "fecha",
                value,
                anio=value.year,
                trimestre=((value.month - 1) // 3) + 1,
                mes=value.month,
                nombre_mes=MONTH_NAMES[value.month],
            )
            date_ids[value] = dimension.id_date

        system_ids: dict[str, int] = {}
        all_systems = sorted(
            {row.sistema for row in generation}
            | {row.sistema for row in sales}
            | {row.sistema for row in capacity}
        )
        for name in all_systems:
            dimension = _get_or_create(
                session,
                DimSistema,
                "nombre_sistema",
                name,
                tipo_sistema=SYSTEM_METADATA[name],
                pais="Chile",
            )
            system_ids[name] = dimension.id_sistema

        technology_ids: dict[str, int] = {}
        all_technologies = sorted(
            {row.tecnologia for row in generation}
            | {row.tecnologia for row in capacity}
        )
        for name in all_technologies:
            category, resource_type, renewable = technology_metadata(name)
            dimension = _get_or_create(
                session,
                DimTecnologia,
                "tecnologia",
                name,
                categoria_tecnologia=category,
                tipo_recurso=resource_type,
                es_renovable=renewable,
            )
            technology_ids[name] = dimension.id_tecnologia

        client_ids: dict[str, int] = {}
        for name in sorted({row.tipo_cliente for row in sales}):
            segment, description = CLIENT_METADATA[name]
            dimension = _get_or_create(
                session,
                DimTipoCliente,
                "tipo_cliente",
                name,
                segmento_cliente=segment,
                descripcion=description,
            )
            client_ids[name] = dimension.id_tipo_cliente

        region_ids: dict[str, int] = {}
        for name in sorted({row.region for row in capacity}):
            dimension = session.scalar(
                select(DimRegion).where(
                    DimRegion.pais == "Chile",
                    DimRegion.region == name,
                )
            )
            if dimension is None:
                dimension = DimRegion(
                    pais="Chile",
                    region=name,
                    zona_geografica=region_zone(name),
                )
                session.add(dimension)
                session.flush()
            else:
                dimension.zona_geografica = region_zone(name)
            region_ids[name] = dimension.id_region

        session.add_all(
            [
                FactGeneracionElectrica(
                    id_date=date_ids[row.fecha],
                    id_sistema=system_ids[row.sistema],
                    id_tecnologia=technology_ids[row.tecnologia],
                    energia_generada_gwh=row.energia_gwh,
                )
                for row in generation
            ]
        )
        session.add_all(
            [
                FactVentasEnergia(
                    id_date=date_ids[row.fecha],
                    id_sistema=system_ids[row.sistema],
                    id_tipo_cliente=client_ids[row.tipo_cliente],
                    energia_vendida_gwh=row.energia_gwh,
                )
                for row in sales
            ]
        )
        session.add_all(
            [
                FactCapacidadInstalada(
                    id_date=date_ids[row.fecha],
                    id_sistema=system_ids[row.sistema],
                    id_tecnologia=technology_ids[row.tecnologia],
                    id_region=region_ids[row.region],
                    nivel_geografico=row.nivel_geografico,
                    capacidad_instalada_mw=row.capacidad_mw,
                )
                for row in capacity
            ]
        )

    engine.dispose()


def print_summary(
    generation: list[GenerationRow],
    sales: list[SalesRow],
    capacity: list[CapacityRow],
) -> None:
    regional = sum(row.nivel_geografico == "REGION" for row in capacity)
    print(f"Generación: {len(generation):,} filas")
    print(f"Ventas: {len(sales):,} filas")
    print(
        f"Capacidad: {len(capacity):,} filas "
        f"({regional:,} regionales y {len(capacity) - regional:,} por sistema)"
    )
    print("Tipos: fechas=date, años/meses/claves=int, medidas=Decimal(20, 6)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Transforma los Excel del CEN y puebla el modelo estrella."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida y resume los Excel sin conectarse a MySQL.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    generation, sales, capacity = extract_all()
    print_summary(generation, sales, capacity)
    if args.dry_run:
        print("Validación terminada; no se modificó la base de datos.")
        return
    populate_database(generation, sales, capacity)
    print("Base de datos poblada correctamente.")


if __name__ == "__main__":
    main()

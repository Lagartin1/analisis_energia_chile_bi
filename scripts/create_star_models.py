"""Crea el esquema dimensional de energía eléctrica en MySQL."""

from __future__ import annotations

import argparse
import os
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    create_engine,
    text,
)
from sqlalchemy.engine import Engine, URL
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


SCRIPT_DIR = Path(__file__).resolve().parent
load_dotenv(SCRIPT_DIR / ".env")


class Base(DeclarativeBase):
    pass


class DimDate(Base):
    __tablename__ = "dim_date"
    __table_args__ = (
        CheckConstraint("anio BETWEEN 1900 AND 2100", name="ck_dim_date_anio"),
        CheckConstraint("trimestre BETWEEN 1 AND 4", name="ck_dim_date_trimestre"),
        CheckConstraint("mes BETWEEN 1 AND 12", name="ck_dim_date_mes"),
    )

    id_date: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    anio: Mapped[int] = mapped_column(Integer, nullable=False)
    trimestre: Mapped[int] = mapped_column(Integer, nullable=False)
    mes: Mapped[int] = mapped_column(Integer, nullable=False)
    nombre_mes: Mapped[str] = mapped_column(String(20), nullable=False)


class DimSistema(Base):
    __tablename__ = "dim_sistema"

    id_sistema: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre_sistema: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    tipo_sistema: Mapped[str | None] = mapped_column(String(100))
    pais: Mapped[str] = mapped_column(String(100), nullable=False, default="Chile")


class DimTecnologia(Base):
    __tablename__ = "dim_tecnologia"

    id_tecnologia: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tecnologia: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    categoria_tecnologia: Mapped[str | None] = mapped_column(String(100))
    tipo_recurso: Mapped[str | None] = mapped_column(String(100))
    es_renovable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class DimRegion(Base):
    __tablename__ = "dim_region"
    __table_args__ = (UniqueConstraint("pais", "region", name="uq_dim_region_pais_region"),)

    id_region: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais: Mapped[str] = mapped_column(String(100), nullable=False, default="Chile")
    zona_geografica: Mapped[str | None] = mapped_column(String(100))
    region: Mapped[str] = mapped_column(String(100), nullable=False)


class DimTipoCliente(Base):
    __tablename__ = "dim_tipo_cliente"

    id_tipo_cliente: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tipo_cliente: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    segmento_cliente: Mapped[str | None] = mapped_column(String(100))
    descripcion: Mapped[str | None] = mapped_column(String(255))


class FactGeneracionElectrica(Base):
    __tablename__ = "fact_generacion_electrica"
    __table_args__ = (
        UniqueConstraint(
            "id_date",
            "id_sistema",
            "id_tecnologia",
            name="uq_fact_generacion_grano",
        ),
        Index("ix_fact_generacion_date", "id_date"),
        Index("ix_fact_generacion_sistema", "id_sistema"),
        Index("ix_fact_generacion_tecnologia", "id_tecnologia"),
        CheckConstraint(
            "energia_generada_gwh >= 0",
            name="ck_fact_generacion_energia_no_negativa",
        ),
    )

    id_generacion: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_date: Mapped[int] = mapped_column(ForeignKey("dim_date.id_date"), nullable=False)
    id_sistema: Mapped[int] = mapped_column(
        ForeignKey("dim_sistema.id_sistema"), nullable=False
    )
    id_tecnologia: Mapped[int] = mapped_column(
        ForeignKey("dim_tecnologia.id_tecnologia"), nullable=False
    )
    energia_generada_gwh: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False
    )

    fecha: Mapped[DimDate] = relationship()
    sistema: Mapped[DimSistema] = relationship()
    tecnologia: Mapped[DimTecnologia] = relationship()


class FactVentasEnergia(Base):
    __tablename__ = "fact_ventas_energia"
    __table_args__ = (
        UniqueConstraint(
            "id_date",
            "id_sistema",
            "id_tipo_cliente",
            name="uq_fact_ventas_grano",
        ),
        Index("ix_fact_ventas_date", "id_date"),
        Index("ix_fact_ventas_sistema", "id_sistema"),
        Index("ix_fact_ventas_cliente", "id_tipo_cliente"),
        CheckConstraint(
            "energia_vendida_gwh >= 0",
            name="ck_fact_ventas_energia_no_negativa",
        ),
    )

    id_venta: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_date: Mapped[int] = mapped_column(ForeignKey("dim_date.id_date"), nullable=False)
    id_sistema: Mapped[int] = mapped_column(
        ForeignKey("dim_sistema.id_sistema"), nullable=False
    )
    id_tipo_cliente: Mapped[int] = mapped_column(
        ForeignKey("dim_tipo_cliente.id_tipo_cliente"), nullable=False
    )
    energia_vendida_gwh: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)

    fecha: Mapped[DimDate] = relationship()
    sistema: Mapped[DimSistema] = relationship()
    tipo_cliente: Mapped[DimTipoCliente] = relationship()


class FactCapacidadInstalada(Base):
    __tablename__ = "fact_capacidad_instalada"
    __table_args__ = (
        UniqueConstraint(
            "id_date",
            "id_sistema",
            "id_tecnologia",
            "id_region",
            name="uq_fact_capacidad_grano",
        ),
        Index("ix_fact_capacidad_date", "id_date"),
        Index("ix_fact_capacidad_sistema", "id_sistema"),
        Index("ix_fact_capacidad_tecnologia", "id_tecnologia"),
        Index("ix_fact_capacidad_region", "id_region"),
        CheckConstraint(
            "nivel_geografico IN ('SISTEMA', 'REGION')",
            name="ck_fact_capacidad_nivel",
        ),
        CheckConstraint(
            "capacidad_instalada_mw >= 0",
            name="ck_fact_capacidad_no_negativa",
        ),
    )

    id_capacidad: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_date: Mapped[int] = mapped_column(ForeignKey("dim_date.id_date"), nullable=False)
    id_sistema: Mapped[int] = mapped_column(
        ForeignKey("dim_sistema.id_sistema"), nullable=False
    )
    id_tecnologia: Mapped[int] = mapped_column(
        ForeignKey("dim_tecnologia.id_tecnologia"), nullable=False
    )
    id_region: Mapped[int] = mapped_column(
        ForeignKey("dim_region.id_region"), nullable=False
    )
    nivel_geografico: Mapped[str] = mapped_column(String(20), nullable=False)
    capacidad_instalada_mw: Mapped[Decimal] = mapped_column(
        Numeric(20, 6), nullable=False
    )

    fecha: Mapped[DimDate] = relationship()
    sistema: Mapped[DimSistema] = relationship()
    tecnologia: Mapped[DimTecnologia] = relationship()
    region: Mapped[DimRegion] = relationship()


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Falta la variable {name} en {SCRIPT_DIR / '.env'}")
    return value.strip()


def database_name() -> str:
    name = _required_env("DB_NAME")
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise RuntimeError("DB_NAME sólo puede contener letras, números y guion bajo.")
    return name


def build_url(include_database: bool = True) -> URL:
    port_value = os.getenv("PORT_DB", "3306").strip()
    try:
        port = int(port_value)
    except ValueError as exc:
        raise RuntimeError("PORT_DB debe ser un número entero.") from exc

    return URL.create(
        "mysql+pymysql",
        username=_required_env("DB_USER"),
        password=_required_env("DB_PASSWORD"),
        host=_required_env("HOST_DB"),
        port=port,
        database=database_name() if include_database else None,
        query={"charset": "utf8mb4"},
    )


def get_database_engine(*, echo: bool = False) -> Engine:
    return create_engine(
        build_url(),
        echo=echo,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )


def create_star_schema(*, echo: bool = False, drop_existing: bool = False) -> Engine:
    schema = database_name()
    server_engine = create_engine(
        build_url(include_database=False),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )
    with server_engine.begin() as connection:
        if drop_existing:
            connection.execute(text(f"DROP DATABASE IF EXISTS `{schema}`"))
        connection.execute(
            text(
                f"CREATE DATABASE IF NOT EXISTS `{schema}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        )
    server_engine.dispose()

    engine = get_database_engine(echo=echo)
    Base.metadata.create_all(engine)
    return engine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crea desde cero las dimensiones y tablas de hechos."
    )
    parser.add_argument(
        "--drop-existing",
        action="store_true",
        help="Elimina completamente el schema configurado antes de volver a crearlo.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    created_engine = create_star_schema(
        echo=False,
        drop_existing=args.drop_existing,
    )
    action = "recreado" if args.drop_existing else "creado"
    print(
        f"Modelo estrella {action} correctamente "
        f"en la base de datos '{database_name()}'."
    )
    created_engine.dispose()

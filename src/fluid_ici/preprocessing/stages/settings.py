"""Portable locations and common DuckDB helpers for the clinical SQL stages."""
from pathlib import Path
import json
import os
import re

import duckdb

DATA = Path(os.environ["FLUID_ICI_RAW_DATA"]).resolve()
ROOT = Path(os.environ["FLUID_ICI_WORK_DIR"]).resolve()
WORK = ROOT / "staged"
OUT = ROOT / "audit"
REF = Path(__file__).resolve().parents[1] / "references"
for path in (WORK, OUT, WORK / "duckdb_temp"):
    path.mkdir(parents=True, exist_ok=True)


def sqlstr(value):
    return "'" + str(value).replace("'", "''") + "'"


def raw(name):
    for suffix in (".csv.gz", ".csv"):
        path = DATA / (name + suffix)
        if path.is_file():
            return (f"read_csv({sqlstr(path)}, header=true, all_varchar=true, "
                    "nullstr='', strict_mode=true, ignore_errors=false)")
    raise FileNotFoundError(f"Required raw MIMIC table not found: {name}")


def pq(name):
    return f"read_parquet({sqlstr(WORK / (name + '.parquet'))})"


def connect():
    threads = int(os.environ.get("FLUID_ICI_THREADS", "4"))
    memory = os.environ.get("FLUID_ICI_MEMORY_LIMIT", "16GB")
    if threads < 1 or not re.fullmatch(r"[1-9][0-9]*(?:MB|GB)", memory):
        raise ValueError("Use positive threads and a memory limit such as 16GB")
    con = duckdb.connect()
    con.execute(f"SET threads={threads}")
    con.execute(f"SET memory_limit={sqlstr(memory)}")
    con.execute(f"SET temp_directory={sqlstr(WORK / 'duckdb_temp')}")
    con.execute("SET preserve_insertion_order=false")
    return con


def save(con, name, query):
    path = WORK / (name + ".parquet")
    temporary = WORK / (name + ".partial.parquet")
    if temporary.exists():
        temporary.unlink()
    con.execute(f"COPY ({query}) TO {sqlstr(temporary)} (FORMAT PARQUET, COMPRESSION ZSTD)")
    temporary.replace(path)
    count = con.execute(f"SELECT count(*) FROM {pq(name)}").fetchone()[0]
    print(f"{name}: {count:,} rows", flush=True)
    return count

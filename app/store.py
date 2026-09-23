"""Registro local (SQLite) de conversaciones, handoffs y demanda no cubierta.

Etapa 1: SQLite para desarrollo. En produccion estas tablas viven en PostgreSQL (db/schema.sql).
No se guarda PII del cliente aqui; session_id es un identificador opaco.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone


class Store:
    def __init__(self, path: str):
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS mensaje (id INTEGER PRIMARY KEY, session_id TEXT, rol TEXT, contenido TEXT,
            modelo TEXT, costo_usd REAL, latencia_ms INTEGER, ts TEXT);
        CREATE TABLE IF NOT EXISTS tool_call (id INTEGER PRIMARY KEY, session_id TEXT, nombre TEXT,
            argumentos TEXT, resultado TEXT, ts TEXT);
        CREATE TABLE IF NOT EXISTS handoff (id INTEGER PRIMARY KEY, session_id TEXT, resumen TEXT, motivo TEXT,
            prioridad TEXT, estado TEXT DEFAULT 'abierto', ts TEXT);
        CREATE TABLE IF NOT EXISTS demanda_no_cubierta (id INTEGER PRIMARY KEY, session_id TEXT, consulta TEXT,
            filtros TEXT, motivo TEXT, ts TEXT);
        """)

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _exec(self, sql: str, params: tuple) -> int:
        with self._lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur.lastrowid

    def log_message(self, session_id, rol, contenido, modelo=None, costo_usd=None, latencia_ms=None):
        return self._exec("INSERT INTO mensaje (session_id, rol, contenido, modelo, costo_usd, latencia_ms, ts) "
                          "VALUES (?,?,?,?,?,?,?)", (session_id, rol, contenido, modelo, costo_usd, latencia_ms, self._now()))

    def log_tool(self, session_id, nombre, argumentos, resultado):
        return self._exec("INSERT INTO tool_call (session_id, nombre, argumentos, resultado, ts) VALUES (?,?,?,?,?)",
                          (session_id, nombre, json.dumps(argumentos, ensure_ascii=False),
                           json.dumps(resultado, ensure_ascii=False), self._now()))

    def create_handoff(self, session_id, resumen, motivo, prioridad):
        return self._exec("INSERT INTO handoff (session_id, resumen, motivo, prioridad, ts) VALUES (?,?,?,?,?)",
                          (session_id, resumen, motivo, prioridad, self._now()))

    def log_unmet_demand(self, session_id, consulta, filtros, motivo):
        return self._exec("INSERT INTO demanda_no_cubierta (session_id, consulta, filtros, motivo, ts) VALUES (?,?,?,?,?)",
                          (session_id, consulta, json.dumps(filtros or {}, ensure_ascii=False), motivo, self._now()))

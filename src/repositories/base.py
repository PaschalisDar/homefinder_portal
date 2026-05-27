"""
Module: repositories.base
Description: Provides low-level database execution helpers and cursor wrappers. 
             Acts as the foundation class for the Repository Pattern.
References:
  - SDS §1.1: Repository-per-aggregate architectural decision (eleven concrete repositories 
    implement narrow interfaces, keeping SQL out of services).
  - SDS Figure 1: Component Diagram (Data Access Layer encapsulation over SQLite).
"""

from models import get_db, row_to_dict

class BaseRepository:
    """
    Abstract base repository providing centralized transactional execution hooks.
    Ensures structural abstraction over direct database connector handles.
    """

    @staticmethod
    def _q(sql: str, params: tuple = (), *, many: bool = False, scalar: bool = False):
        """
        Executes a SQL query statement and serializes relational cursors into structured results.
        Supports single row, multiple rows, or single data-point (scalar) extractions.
        """
        with get_db() as conn:
            cur = conn.execute(sql, params)
            if scalar:
                row = cur.fetchone()
                return row[0] if row else None
            if many:
                return [row_to_dict(r) for r in cur.fetchall()]
            row = cur.fetchone()
            return row_to_dict(row) if row else None

    @staticmethod
    def _exec(sql: str, params: tuple = ()):
        """
        Executes an atomic Data Manipulation Language (DML) statement (INSERT, UPDATE, DELETE).
        Returns the primary integer key identifier of the modified or created row.
        """
        with get_db() as conn:
            cur = conn.execute(sql, params)
            return cur.lastrowid
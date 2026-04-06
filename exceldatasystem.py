import pandas as pd
import os
from typing import Union, List, Dict
from basestorage import BaseStorage


class ExcelStorage(BaseStorage):
    def __init__(self, filepath, engine='xlsxwriter'):
        self.filepath = filepath
        self.engine = engine  # default to xlsxwriter for formatting capabilities

    def load(self, sheet_name: str|int = 0) -> List[Dict]:
        """
        Accepts sheet_name as a string ("Users") or an int (0).
        Defaults to 0 (the first sheet).
        """
        if not os.path.exists(self.filepath):
            return []
        try:
            # Pandas naturally handles both str and int for sheet_name
            df = pd.read_excel(self.filepath, sheet_name=sheet_name)
            return df.to_dict(orient="records")
        except Exception as e:
            print(f"⚠️ Load failed: {e}")
            return []

    def save(self, data:list | dict, sheet_name:str | int="Sheet1", columns: list | dict = None,format_func=None, **kwargs):
        """
        Saves data to Excel.
        - data: List of dicts (single sheet) OR Dict of {sheet_name: list of dicts} (multi-sheet)
        - columns: List of column names to enforce order, or Dict to rename headers.
        - format_func: A callback function to apply custom xlsxwriter formatting.
        """
        with pd.ExcelWriter(self.filepath, engine=self.engine) as writer:

            # --- MULTI-SHEET HANDLING ---
            if isinstance(data, dict):
                for s_name, s_data in data.items():
                    # Get the specific columns for this sheet (if provided)
                    s_cols = columns.get(s_name) if isinstance(columns, dict) else None

                    # Case A: Data is a List of Lists (like final_rows)
                    if isinstance(s_data, list) and len(s_data) > 0 and isinstance(s_data[0], list):
                        df = pd.DataFrame(s_data, columns=s_cols)

                    # Case B: Data is a List of Dicts (like unassigned_users)
                    else:
                        df = pd.DataFrame(s_data)
                        if s_cols and isinstance(s_cols, list):
                            # Filter to keep only the requested columns
                            valid_cols = [c for c in s_cols if c in df.columns]
                            df = df[valid_cols]

                    df.to_excel(writer, sheet_name=s_name, index=False)

            # --- SINGLE-SHEET HANDLING ---
            else:
                if isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                    df = pd.DataFrame(data, columns=columns)
                else:
                    df = pd.DataFrame(data)
                    if columns:
                        df = df.reindex(columns=columns) if isinstance(columns, list) else df.rename(columns=columns)

                df.to_excel(writer, sheet_name=sheet_name, index=False)

            # --- 2. FORMATTING TRIGGER (The Missing Piece) ---
            # This checks if you passed a formatting function AND if the engine supports it
            if format_func and self.engine == 'xlsxwriter':
                workbook = writer.book

                # Figure out which sheets we just created so we can format them
                sheet_names_written = data.keys() if isinstance(data, dict) else [sheet_name]

                for s_name in sheet_names_written:
                    worksheet = writer.sheets[s_name]
                    # Execute the factory function you passed in
                    format_func(workbook, worksheet, s_name)

    def append(self, record, sheet_name:str | int="Sheet1", **kwargs):
        """Load, add one, and save back to the same sheet."""
        data = self.load(sheet_name=sheet_name)
        data.append(record)
        self.save(data, sheet_name=sheet_name, **kwargs)

    def remove(self, record, sheet_name:str | int="Sheet1", **kwargs):
        """Load, remove one, and save back."""
        data = self.load(sheet_name=sheet_name)
        if record in data:
            data.remove(record)
        self.save(data, sheet_name=sheet_name, **kwargs)

    def getfilepath(self):
        return self.filepath
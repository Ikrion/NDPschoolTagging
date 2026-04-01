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

    def save(self, data:list | dict, sheet_name:str | int="Sheet1", columns:str | int=None, format_func=None, **kwargs):
        """
        Saves data to Excel.
        - data: List of dicts (single sheet) OR Dict of {sheet_name: list of dicts} (multi-sheet)
        - columns: List of column names to enforce order, or Dict to rename headers.
        - format_func: A callback function to apply custom xlsxwriter formatting.
        """
        dfs = {}

        # 1. Handle Single vs Multi-Sheet data structures
        if isinstance(data, dict):
            # User passed {'Sheet1': [...], 'Sheet2': [...]}
            for s_name, s_data in data.items():
                dfs[s_name] = pd.DataFrame(s_data)
        else:
            # User passed a standard list of records [...]
            dfs[sheet_name] = pd.DataFrame(data)

        # 2. Handle Column logic
        for s_name, df in dfs.items():
            if columns:
                if isinstance(columns, list):
                    dfs[s_name] = df.reindex(columns=columns)  # Enforce order/selection
                elif isinstance(columns, dict):
                    dfs[s_name] = df.rename(columns=columns)  # Rename existing

        # 3. Save to Excel & Apply Formatting (Optional)
        with pd.ExcelWriter(self.filepath, engine=self.engine) as writer:
            for s_name, df in dfs.items():
                df.to_excel(writer, sheet_name=s_name, index=False)

            # 4. Trigger the optional formatting callback
            if format_func and self.engine == 'xlsxwriter':
                workbook = writer.book
                for s_name in dfs.keys():
                    worksheet = writer.sheets[s_name]
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
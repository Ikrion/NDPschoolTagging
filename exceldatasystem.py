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

            workbook = writer.book
            header_fmt = workbook.add_format({
                "bold": True,
                "bg_color": "#F2F2F2",
                "border": 1
            })

            # ---------------- MULTI SHEET ----------------
            if isinstance(data, dict):

                for s_name, s_data in data.items():

                    # Get the columns for this sheet
                    s_cols = columns.get(s_name) if isinstance(columns, dict) else None

                    # ---------------- Create DataFrame ----------------

                    # List of Lists
                    if (
                            isinstance(s_data, list)
                            and len(s_data) > 0
                            and isinstance(s_data[0], list)
                    ):
                        df = pd.DataFrame(s_data, columns=s_cols)

                    # List of Dicts / Dict
                    else:
                        df = pd.DataFrame(s_data)

                        if s_cols and isinstance(s_cols, list):
                            valid_cols = [c for c in s_cols if c in df.columns]
                            df = df[valid_cols]

                    # ---------------- Write Excel ----------------

                    df.to_excel(writer, sheet_name=s_name, index=False)

                    worksheet = writer.sheets[s_name]

                    # --------------- Highlight col head -----------
                    for col_num, header in enumerate(df.columns):
                        worksheet.write(0, col_num, header, header_fmt)

                    # ---------------- Auto Width ----------------

                    for col_num, column in enumerate(df.columns):

                        # Header width
                        max_length = len(str(column))

                        # Data width
                        for value in df.iloc[:, col_num]:
                            value_length = len(str(value)) if value is not None else 0
                            max_length = max(max_length, value_length)

                        worksheet.set_column(
                            col_num,
                            col_num,
                            min(max(max_length + 2, 10), 50)
                        )


                    # ---------------- Freeze Header ----------------

                    worksheet.freeze_panes(1, 0)

                    # ---------------- Filter ----------------

                    if not df.empty:
                        worksheet.autofilter(
                            0,
                            0,
                            len(df),
                            len(df.columns) - 1
                        )

                    # ---------------- Alternate Rows ----------------

                    alternate = workbook.add_format({
                        "bg_color": "#F8F8F8"
                    })

                    worksheet.conditional_format(
                        1,
                        0,
                        len(df),
                        len(df.columns) - 1,
                        {
                            "type": "formula",
                            "criteria": "=MOD(ROW(),2)=0",
                            "format": alternate,
                        }
                    )

                    # ---------------- Custom Formatting ----------------

                    if format_func and self.engine == "xlsxwriter":
                        format_func(workbook, worksheet, s_name)

            # ---------------- SINGLE SHEET ----------------
            else:

                if (
                        isinstance(data, list)
                        and len(data) > 0
                        and isinstance(data[0], list)
                ):
                    df = pd.DataFrame(data, columns=columns)

                else:
                    df = pd.DataFrame(data)

                    if columns:
                        df = (
                            df.reindex(columns=columns)
                            if isinstance(columns, list)
                            else df.rename(columns=columns)
                        )

                df.to_excel(writer, sheet_name=sheet_name, index=False)

                worksheet = writer.sheets[sheet_name]

                # --------------- Highlight col head -----------
                for col_num, header in enumerate(df.columns):
                    worksheet.write(0, col_num, header, header_fmt)

                # Auto Width
                for col_num, column in enumerate(df.columns):

                    # Header width
                    max_length = len(str(column))

                    # Data width
                    for value in df.iloc[:, col_num]:
                        value_length = len(str(value)) if value is not None else 0
                        max_length = max(max_length, value_length)

                    worksheet.set_column(
                        col_num,
                        col_num,
                        min(max(max_length + 2, 10), 50)
                    )

                worksheet.freeze_panes(1, 0)

                if not df.empty:
                    worksheet.autofilter(
                        0,
                        0,
                        len(df),
                        len(df.columns) - 1
                    )

                alternate = workbook.add_format({
                    "bg_color": "#F8F8F8"
                })

                worksheet.conditional_format(
                    1,
                    0,
                    len(df),
                    len(df.columns) - 1,
                    {
                        "type": "formula",
                        "criteria": "=MOD(ROW(),2)=0",
                        "format": alternate,
                    }
                )

                if format_func and self.engine == "xlsxwriter":
                    format_func(workbook, worksheet, sheet_name)


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
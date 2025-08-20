#!/usr/bin/env python
"""Simple migration to comment out all non-migrated routes."""

import re
from pathlib import Path


def migrate():
    admin_ui = Path("admin_ui.py")
    content = admin_ui.read_text()

    # Find all @app.route decorators that aren't commented
    pattern = r"^(@app\.route\(.*?\))"

    lines = content.split("\n")
    new_lines = []
    in_function = False
    function_depth = 0

    for _i, line in enumerate(lines):
        # Check if this is an uncommented route
        if re.match(r"^@app\.route\(", line):
            # Mark as in function
            in_function = True
            function_depth = 0
            # Comment it out
            new_lines.append("# MIGRATED to blueprint")
            new_lines.append("# " + line)
        elif in_function:
            # Count indentation to track function boundaries
            if line.strip() and not line.startswith("#"):
                if line.startswith("def "):
                    function_depth = len(line) - len(line.lstrip())
                elif (
                    line.strip()
                    and (len(line) - len(line.lstrip())) <= function_depth
                    and not line.startswith(" " * (function_depth + 4))
                ):
                    # End of function
                    if line.startswith("@") or line.startswith("def ") or line.startswith("class "):
                        in_function = False
                        new_lines.append(line)
                        continue

            # Comment out function body
            if line.strip() or in_function:
                new_lines.append("# " + line if line.strip() else line)
            else:
                in_function = False
                new_lines.append(line)
        else:
            new_lines.append(line)

    # Write back
    admin_ui.write_text("\n".join(new_lines))
    print("Migration complete!")


if __name__ == "__main__":
    migrate()

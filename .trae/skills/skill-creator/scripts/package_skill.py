#!/usr/bin/env python3
"""Package a skill into a .skill file."""

import zipfile
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("skill_dir", type=Path, help="Path to skill directory")
    parser.add_argument("--output", type=Path, help="Output .skill file path")
    args = parser.parse_args()

    skill_dir = args.skill_dir
    if not skill_dir.exists() or not skill_dir.is_dir():
        print(f"Error: {skill_dir} is not a valid directory")
        return 1

    if not (skill_dir / "SKILL.md").exists():
        print(f"Error: {skill_dir} does not contain SKILL.md")
        return 1

    output_path = args.output
    if not output_path:
        output_path = skill_dir.parent / f"{skill_dir.name}.skill"

    # Create zip file
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add all files in skill directory
        for root, dirs, files in skill_dir.walk():
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(skill_dir)
                zf.write(file_path, arcname)

    print(f"Skill packaged successfully to {output_path}")
    return 0


if __name__ == "__main__":
    exit(main())

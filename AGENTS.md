## Codebase Instructions
### Data Format
*   The primary data source is the **FC2 file format** (`.fc2` extension), derived from Potensic drones (Atom-2). This data can be viewed through specific field definitions (e.g., micro seconds since start at byte 5, accelerometer readings at byte 19, etc.).
*   **Critical:** The FC2 record format and content are volatile and change with firmware updates. The structure provided in the `README.md` is the current best guess, but agents must treat it as such.

### Core Execution Workflow
*   **Conversion Tool:** Always use `atom_data_extractor.py` for conversion.
    *   **Command Structure:** `atom_data_extractor.py [files ...] -D <destination> -l <log_level> -x`
    *   **Output:** Converts `.fc2` logs into a CSV file (`.csv`) in the specified or default directory.
    *   **Skipping Records:** The tool automatically skips records with unrecognized data, which is intentional for maintaining compatibility with external tools like Telemetry Overlay.
*   **Testing:** Specific tests exist for `ade.spec` and `adv.spec` in the `src` directory. Use `pytest` or the appropriate test command defined in `package.json` (if applicable) to verify functionality.

### Developer Commands and Setup Quirks
*   **Building GUI:** To build the GUI applications, one must execute the build process from the project root:
    1.  `python3 -m venv ade-venv`
    2.  `source ade-venv/bin/activate`
    3.  `pip install -r requirements.txt`
    4.  (On Ubuntu) `sudo apt install python3-tk`
    5.  `cd src`
    6.  `./build.sh`
*   **Environment:** The CLI version of the extractor can be run directly using `python3 atom_data_extractor.py <fc2 file>` after copying the script to the user's bin directory.

### Operational Gotchas
*   **Time Syncing:** When using the generated CSV data in Telemetry Overlay, manual time synchronization between the video file and the telemetry data is often required, as the FC2 file name provides the only explicit time stamp.
*   **Data Fields:** The file's meta-data and specific field bytes (e.g., GNSS coordinates, motor states) are crucial for understanding the data, but accessing them requires consulting the `README.md`'s detailed section.

## What to avoid
*   Do not assume the FC2 file structure is stable across firmware versions.
*   Do not output generic advice; focus on commands and file locations.
</content

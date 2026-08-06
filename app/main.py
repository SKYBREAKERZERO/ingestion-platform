from pathlib import Path

from app.pipeline.pipeline_factory import PipelineFactory


INPUT_DIR = Path("./input")
OUTPUT_DIR = Path("./output")


def main() -> None:

    INPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    files = sorted(
        (
            file
            for file in INPUT_DIR.iterdir()
            if (
                file.is_file()
                and not file.name.startswith("~$")
                and PipelineFactory.supports(file)
            )
        ),
        key=lambda file: (
            file.suffix.lower(),
            file.name.lower(),
        ),
    )

    if not files:
        print(
            "No supported input files found."
        )
        return

    success_count = 0
    failure_count = 0

    for file_path in files:

        output_path = (
            OUTPUT_DIR
            / f"{file_path.stem}.json"
        )

        print()
        print("====================")
        print(
            f"Processing: {file_path.name}"
        )
        print("====================")

        try:
            pipeline = PipelineFactory.create(
                file_path
            )

            print(
                "Pipeline:",
                pipeline.__class__.__name__,
            )

            document = pipeline.run(
                file_path=file_path,
                output=output_path,
            )

            success_count += 1

            print("Completed")
            print(
                "Pages:",
                len(document.pages),
            )
            print(
                "Chapters:",
                len(document.chapters),
            )
            print(
                "Sections:",
                len(document.sections),
            )
            print(
                "Contents:",
                len(document.contents),
            )
            print(
                "Output:",
                output_path,
            )

        except Exception as exc:
            failure_count += 1

            print(
                f"Failed: {file_path.name}"
            )
            print(exc)

    print()
    print("====================")
    print("Batch Summary")
    print("====================")
    print(
        "Success:",
        success_count,
    )
    print(
        "Failed:",
        failure_count,
    )
    print(
        "Total:",
        len(files),
    )


if __name__ == "__main__":
    main()
import argparse

from config import INPUT_IR_PATH, OUTPUT_DIR, MANIFEST_DIR
from loaders import load_ir_records
from package_builder import build_all_packages_for_ir
from artifacts import write_all_artifacts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(INPUT_IR_PATH))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--manifest-dir", default=str(MANIFEST_DIR))
    args = parser.parse_args()

    ir_records = load_ir_records(args.input)

    packages = []
    for ir in ir_records:
        packages.extend(build_all_packages_for_ir(ir))

    quality_report = write_all_artifacts(
        packages=packages,
        ir_records=ir_records,
        output_dir=args.output_dir,
        manifest_dir=args.manifest_dir,
        input_path=args.input,
    )

    print(f"Batch I0 status: {quality_report.get('status')}")
    print(f"Input IR records: {quality_report.get('input_ir_record_count')}")
    print(f"Output packages: {quality_report.get('output_package_count')}")


if __name__ == "__main__":
    main()
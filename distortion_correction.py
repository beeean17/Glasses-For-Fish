import argparse
import json
import os

import cv2 as cv
import numpy as np


def load_calibration_results(result_file):
    with open(result_file, "r") as f:
        results = json.load(f)

    camera_matrix = np.array(results["K"], dtype=np.float64)
    dist_coeffs = np.array(results["dist_coef"], dtype=np.float64)
    distortion_model = results["score_best_model"]["dist_model"]

    return results, camera_matrix, dist_coeffs, distortion_model


def is_video_file(path):
    return os.path.splitext(path)[1].lower() in {".mp4", ".avi", ".mov", ".mkv", ".m4v"}


def is_image_file(path):
    return os.path.splitext(path)[1].lower() in {
        ".png",
        ".jpg",
        ".jpeg",
        ".bmp",
        ".gif",
        ".tiff",
        ".webp",
        ".jp2",
    }


def make_output_path(output_path):
    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def ensure_output_dir(output_dir):
    os.makedirs(output_dir, exist_ok=True)


def undistort_frame(frame, camera_matrix, dist_coeffs, distortion_model, balance=0.0):
    height, width = frame.shape[:2]

    if distortion_model.startswith("KB"):
        new_camera_matrix = cv.fisheye.estimateNewCameraMatrixForUndistortRectify(
            camera_matrix,
            dist_coeffs,
            (width, height),
            np.eye(3),
            balance=balance,
        )
        map1, map2 = cv.fisheye.initUndistortRectifyMap(
            camera_matrix,
            dist_coeffs,
            np.eye(3),
            new_camera_matrix,
            (width, height),
            cv.CV_16SC2,
        )
        return cv.remap(frame, map1, map2, interpolation=cv.INTER_LINEAR, borderMode=cv.BORDER_CONSTANT)

    new_camera_matrix, _ = cv.getOptimalNewCameraMatrix(
        camera_matrix,
        dist_coeffs,
        (width, height),
        alpha=balance,
        newImgSize=(width, height),
    )
    return cv.undistort(frame, camera_matrix, dist_coeffs, None, new_camera_matrix)


def make_side_by_side(original, corrected):
    return np.hstack([original, corrected])


def process_image_file(input_file, output_file, camera_matrix, dist_coeffs, distortion_model, side_by_side=False, balance=0.0):
    image = cv.imread(input_file)
    if image is None:
        raise FileNotFoundError(f"Could not read image: {input_file}")

    corrected = undistort_frame(image, camera_matrix, dist_coeffs, distortion_model, balance=balance)
    output_image = make_side_by_side(image, corrected) if side_by_side else corrected

    make_output_path(output_file)
    cv.imwrite(output_file, output_image)
    return output_file


def process_image_directory(input_dir, output_dir, camera_matrix, dist_coeffs, distortion_model, side_by_side=False, balance=0.0):
    ensure_output_dir(output_dir)
    image_files = sorted(
        file_name for file_name in os.listdir(input_dir) if is_image_file(file_name)
    )

    if not image_files:
        raise FileNotFoundError(f"No image files found in: {input_dir}")

    saved_files = []
    for file_name in image_files:
        input_file = os.path.join(input_dir, file_name)
        output_file = os.path.join(output_dir, file_name)
        saved_files.append(
            process_image_file(
                input_file,
                output_file,
                camera_matrix,
                dist_coeffs,
                distortion_model,
                side_by_side=side_by_side,
                balance=balance,
            )
        )
    return saved_files


def process_video_file(input_file, output_file, camera_matrix, dist_coeffs, distortion_model, side_by_side=False, balance=0.0):
    capture = cv.VideoCapture(input_file)
    if not capture.isOpened():
        raise FileNotFoundError(f"Could not open video: {input_file}")

    fps = capture.get(cv.CAP_PROP_FPS) or 30.0
    width = int(capture.get(cv.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv.CAP_PROP_FRAME_HEIGHT))
    output_width = width * 2 if side_by_side else width

    make_output_path(output_file)
    writer = cv.VideoWriter(
        output_file,
        cv.VideoWriter_fourcc(*"mp4v"),
        fps,
        (output_width, height),
    )

    while True:
        valid_frame, frame = capture.read()
        if not valid_frame:
            break

        corrected = undistort_frame(frame, camera_matrix, dist_coeffs, distortion_model, balance=balance)
        output_frame = make_side_by_side(frame, corrected) if side_by_side else corrected
        writer.write(output_frame)

    capture.release()
    writer.release()
    return output_file


def main():
    parser = argparse.ArgumentParser(
        prog="distortion_correction",
        description="Apply lens distortion correction using calibration results.",
    )
    parser.add_argument("input_path", type=str, help="Image, directory, or video path to correct")
    parser.add_argument("output_path", type=str, help="Output image/file or output directory")
    parser.add_argument(
        "-r",
        "--result_file",
        default="results.json",
        type=str,
        help="Calibration result json file",
    )
    parser.add_argument(
        "--side_by_side",
        action="store_true",
        help="Save original and corrected frames side by side",
    )
    parser.add_argument(
        "--balance",
        default=0.0,
        type=float,
        help="Undistortion balance. 0 keeps less black border, 1 keeps more FoV.",
    )
    args = parser.parse_args()

    _, camera_matrix, dist_coeffs, distortion_model = load_calibration_results(args.result_file)

    if os.path.isdir(args.input_path):
        saved_files = process_image_directory(
            args.input_path,
            args.output_path,
            camera_matrix,
            dist_coeffs,
            distortion_model,
            side_by_side=args.side_by_side,
            balance=args.balance,
        )
        print(f"Saved {len(saved_files)} corrected images to {args.output_path}")
        return

    if is_video_file(args.input_path):
        saved_file = process_video_file(
            args.input_path,
            args.output_path,
            camera_matrix,
            dist_coeffs,
            distortion_model,
            side_by_side=args.side_by_side,
            balance=args.balance,
        )
        print(f"Saved corrected video to {saved_file}")
        return

    saved_file = process_image_file(
        args.input_path,
        args.output_path,
        camera_matrix,
        dist_coeffs,
        distortion_model,
        side_by_side=args.side_by_side,
        balance=args.balance,
    )
    print(f"Saved corrected image to {saved_file}")


if __name__ == "__main__":
    main()

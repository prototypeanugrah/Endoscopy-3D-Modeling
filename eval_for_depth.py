import os

# from PIL import Image
import cv2
import numpy as np
import glob

INPUT_PATH = "./datasets/SyntheticColon/"

warning1 = False
warning2 = False


def check_depth(pred):
    global warning1, warning2
    assert pred.shape == (
        475,
        475,
    ), "Wrong size of predicted depth, expected [475,475], got {}".format(
        list(pred.shape)
    )
    # assert pred.dtype == np.float16, "Wrong data type, expected float16, got {}".format(
    #     pred.dtype
    # )
    if np.max(pred) > 1:
        if not warning1:
            print("Warning: Depths > 20cm encountered")
        warning1 = True
    if np.min(pred) < 0:
        if not warning2:
            print("Warning: Depths < 0cm encountered")
        warning2 = True

    # return pred.clip(0, 1)  # depths are clipped to (0,1) to avoid invalid depths


# def load_depth(pred_file, gt_file):
#     gt_depth = (
#         np.array(Image.open(gt_file.replace("FrameBuffer", "Depth"))) / 255 / 256
#     )  # please use this to load ground truth depth during training and testing
#     pred = (
#         np.array(Image.open(pred_file).convert("L")).astype(np.float16) / 255 / 256
#     )  # np.load(pred_file)
#     pred = check_depth(pred)

#     # Resize ground truth to match prediction size
#     gt_depth = np.array(
#         Image.fromarray(gt_depth).resize(
#             (pred.shape[1], pred.shape[0]),
#             Image.BILINEAR,
#         )
#     )
#     return pred, gt_depth


def load_depth(pred_file, gt_file):
    # Load ground truth depth using cv2
    gt_depth = cv2.imread(
        gt_file.replace("FrameBuffer", "Depth"),
        cv2.IMREAD_UNCHANGED,
    ).astype(np.float32)
    # print(f"GT shape: {gt_depth.shape}")
    # print(f"GT dtype: {gt_depth.dtype}")
    # print(f"GT min/max: {gt_depth.min()}, {gt_depth.max()}")
    # gt_depth = gt_depth / 255 / 256  # normalize to [0,1] range
    gt_depth = (gt_depth - gt_depth.min()) / (gt_depth.max() - gt_depth.min())
    # print(f"GT min/max after norm: {gt_depth.min()}, {gt_depth.max()}")

    # Load prediction depth using cv2
    pred = cv2.imread(pred_file, cv2.IMREAD_GRAYSCALE).astype(np.float32)
    # print(f"Prediction shape: {pred.shape}")
    # print(f"Prediction dtype: {pred.dtype}")
    # print(f"Prediction min/max: {pred.min()}, {pred.max()}")
    pred = pred / 255.0  # normalize to [0,1] range
    # print(f"Prediction min/max after norm: {pred.min()}, {pred.max()}")

    # Create valid mask
    # valid_mask = (gt_depth > 0) & (gt_depth < 1.0)
    valid_mask = np.isnan(gt_depth) == 0
    gt_depth[valid_mask == 0] = 0

    check_depth(pred)

    # Resize ground truth to match prediction size
    gt_depth = cv2.resize(
        gt_depth,
        (pred.shape[1], pred.shape[0]),
        interpolation=cv2.INTER_LINEAR,
    )
    # print(f"Size of valid_mask: {valid_mask.shape}")
    # exit(0)
    # valid_mask = cv2.resize(
    #     valid_mask.astype(np.float32),
    #     (pred.shape[1], pred.shape[0]),
    #     interpolation=cv2.INTER_NEAREST,
    # ).astype(bool)

    return pred, gt_depth, valid_mask


# def eval_depth(pred, gt_depth):
#     # * 20 to get centimeters
#     diff = pred - gt_depth
#     epsilon = 1e-6  # Small positive constant
#     l1_error = np.mean(np.abs(diff))
#     abs_rel = np.mean(np.abs(diff) / (gt_depth + epsilon))
#     rmse_error = np.sqrt(np.mean((diff) ** 2))
#     # δ<1.1 (percentage of pixels within 10% of actual depth)
#     thresh = np.maximum(
#         (gt_depth / (pred + epsilon)),  # Add epsilon to pred
#         ((pred + epsilon) / (gt_depth + epsilon)),  # Add epsilon to both
#     )
#     d1 = np.mean(thresh < 1.1)
#     return l1_error, abs_rel, d1, rmse_error


def eval_depth(pred, gt_depth, valid_mask):
    # Only evaluate on valid pixels
    pred_valid = pred[valid_mask]
    gt_valid = gt_depth[valid_mask]

    epsilon = 1e-6

    # Calculate metrics on valid pixels only
    diff = pred_valid - gt_valid
    valid_denominator = (valid_mask == 1) & (gt_valid >= 0.000001) & (gt_valid <= 1.0)

    l1_error = np.mean(np.abs(diff))
    abs_rel = np.mean(
        np.abs(diff)[valid_denominator] / (gt_valid[valid_denominator] + epsilon)
    )
    rmse_error = np.sqrt(np.mean(diff**2))

    # δ<1.1 calculation
    thresh = np.maximum(
        (gt_valid / (pred_valid + epsilon)),
        ((pred_valid + epsilon) / (gt_valid + epsilon)),
    )
    d1 = np.mean(thresh < 1.1)

    return l1_error, abs_rel, d1, rmse_error


def process_depths(test_folders, INPUT_PATH):
    # first check if all the data is there
    for traj in test_folders:
        assert os.path.exists(INPUT_PATH + traj + "/"), "No input folder found"
        input_file_list = np.sort(glob.glob(INPUT_PATH + traj + "/Depth*.png"))
        if traj[18] == "I":
            assert len(input_file_list) == 601, "Predictions missing in {}".format(traj)
        else:
            assert len(input_file_list) == 1201, "Predictions missing in {}".format(
                traj
            )

    # loop through predictions
    for traj in test_folders:
        print("Processing ", traj)
        input_file_list = np.sort(glob.glob(INPUT_PATH + traj + "/Depth*.png"))
        l1_errors, abs_rels, d1_err, rmses = [], [], [], []

        # Process all frames in trajectory
        for i in range(len(input_file_list)):
            file_name1 = input_file_list[i].split("/")[-1]
            im1_path = input_file_list[i]
            gt_depth_path = INPUT_PATH + traj.strip("_OP") + "/" + file_name1

            # Load depths and valid mask
            pred_depth, gt_depth, valid_mask = load_depth(
                im1_path,
                gt_depth_path,
            )

            # Calculate metrics for this frame
            l1_error, abs_rel, d1, rmse = eval_depth(
                pred_depth,
                gt_depth,
                valid_mask,
            )

            # Store metrics
            l1_errors.append(l1_error)
            abs_rels.append(abs_rel)
            d1_err.append(d1)
            rmses.append(rmse)

        # Print mean metrics for this trajectory
        print(f"Results for trajectory {traj}:")
        print(f"Mean L1 error: {np.mean(l1_errors):.6f}")
        print(f"Mean AbsRel error: {np.mean(abs_rels):.6f}")
        print(f"Mean δ<1.1: {np.mean(d1_err):.6f}")
        print(f"Mean RMSE: {np.mean(rmses):.6f}")
        print("-" * 50)

        # Optional: Save metrics to file
        # metrics_dict = {
        #     "trajectory": traj,
        #     "l1_error": np.mean(l1_errors),
        #     "abs_rel": np.mean(abs_rels),
        #     "d1": np.mean(d1_err),
        #     "rmse": np.mean(rmses),
        # }

        # You could save the metrics to a file if needed
        # with open(f'metrics_{traj.replace("/", "_")}.txt', 'w') as f:
        #     for key, value in metrics_dict.items():
        #         f.write(f'{key}: {value}\n')

    # Print overall metrics across all trajectories
    print("\nOverall Results:")
    print(f"Overall Mean L1 error: {np.mean(l1_errors):.6f}")
    print(f"Overall Mean AbsRel error: {np.mean(abs_rels):.6f}")
    print(f"Overall Mean δ<1.1: {np.mean(d1_err):.6f}")
    print(f"Overall Mean RMSE: {np.mean(rmses):.6f}")


# def process_depths(test_folders, INPUT_PATH):
#     # first check if all the data is there
#     for traj in test_folders:
#         # print(traj)
#         assert os.path.exists(INPUT_PATH + traj + "/"), "No input folder found"
#         input_file_list = np.sort(glob.glob(INPUT_PATH + traj + "/Depth*.png"))
#         if traj[18] == "I":
#             assert len(input_file_list) == 601, "Predictions missing in {}".format(traj)
#         else:
#             assert len(input_file_list) == 1201, "Predictions missing in {}".format(
#                 traj
#             )

#     # loop through predictions
#     for traj in test_folders:
#         print("Processing ", traj)
#         input_file_list = np.sort(glob.glob(INPUT_PATH + traj + "/Depth*.png"))
#         l1_errors, abs_rels, d1_err, rmses = [], [], [], []
#         preds, gts = [], []
#         for i in range(len(input_file_list)):
#             file_name1 = input_file_list[i].split("/")[-1]
#             # print(file_name1)
#             im1_path = input_file_list[i]
#             gt_depth_path = (
#                 INPUT_PATH
#                 + traj.strip("_OP")
#                 + "/"
#                 + file_name1  # .replace("npy", "png")
#             )
#             pred_depth, gt_depth = load_depth(im1_path, gt_depth_path)
#             preds.append(pred_depth)
#             gts.append(gt_depth)
#         # gts_ = np.mean(np.mean(np.array(gts), 1), 1)
#         # preds_ = np.mean(np.mean(np.array(preds), 1), 1)
#         # scale = np.sum(preds_ * gts_) / np.sum(
#         #     preds_ * preds_
#         # )  # monocular methods predict depth up to scale
#         # print("Scale: ", scale)

#         for i in range(len(input_file_list)):
#             l1_error, abs_rel, d1, rmse = eval_depth(
#                 preds[i],
#                 gts[i],
#             )
#             l1_errors.append(l1_error)
#             abs_rels.append(abs_rel)
#             d1_err.append(d1)
#             rmses.append(rmse)
#         print("Mean L1 error in cm: ", np.mean(l1_errors))
#         print("Mean AbsRel error in cm: ", np.mean(abs_rels))
#         print("Median d1 error in cm: ", np.mean(d1_err))
#         print("Mean RMSE in cm: ", np.mean(rmses))


def main():
    # The 9 test sequences have to organized in the submission .zip file as follows:
    test_folders = [
        "/SyntheticColon_I/Frames_S5_OP",
        "/SyntheticColon_I/Frames_S10_OP",
        "/SyntheticColon_I/Frames_S15_OP",
        "/SyntheticColon_II/Frames_B5_OP",
        "/SyntheticColon_II/Frames_B10_OP",
        "/SyntheticColon_II/Frames_B15_OP",
        "/SyntheticColon_III/Frames_O1_OP",
        "/SyntheticColon_III/Frames_O2_OP",
        "/SyntheticColon_III/Frames_O3_OP",
    ]

    process_depths(test_folders, INPUT_PATH)


if __name__ == "__main__":
    main()

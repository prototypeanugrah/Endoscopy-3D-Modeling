"""
This script is used to generate depth maps for images or videos using the 
fine-tuned Depth Anything V2 model.

Usage:
    python run.py \
    -i <image_path> \
    -o <output_dir> \
    -d <dataset_type> \
    --encoder <encoder> \
    --load-from <checkpoint> \
    --max-depth <max_depth> \
    --save-numpy \
    --pred-only \
    --grayscale
    
Arguments:
    -i, --img-path: Path to the image or text file containing image paths.
    -o, --outdir: Output directory to save the depth maps.
    -d, --ds_type: Dataset type - simcol or testing.
    
    --encoder: Encoder type - vits, vitb, vitl, vitg.
    --load-from: Path to the checkpoint file.
    --max-depth: Maximum depth value.
    
    --save-numpy: Save the model raw output.
    --pred-only: Only display the prediction.
    --grayscale: Do not apply colorful palette.
    

"""

import argparse
import os
import glob

from pathlib import Path
from tqdm import tqdm
import cv2
import matplotlib
import numpy as np
import torch

from Depth_Anything_V2.metric_depth.depth_anything_v2.dpt import DepthAnythingV2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Depth Anything V2 Metric Depth Estimation"
    )

    parser.add_argument("-i", "--img-path", type=str)
    parser.add_argument("--input-size", type=int, default=518)
    parser.add_argument("-o", "--outdir", type=str)
    parser.add_argument("-d", "--ds_type", type=str)

    parser.add_argument(
        "--encoder",
        type=str,
        default="vitl",
        choices=["vits", "vitb", "vitl", "vitg"],
    )
    parser.add_argument(
        "--load-from",
        type=str,
        default="base_checkpoints/depth_anything_v2_metric_hypersim_vitl.pth",
    )
    parser.add_argument("--max-depth", type=float, default=20)

    parser.add_argument(
        "--save-numpy",
        dest="save_numpy",
        action="store_true",
        help="save the model raw output",
    )
    parser.add_argument(
        "--pred-only",
        dest="pred_only",
        action="store_true",
        help="only display the prediction",
    )
    parser.add_argument(
        "--grayscale",
        dest="grayscale",
        action="store_true",
        help="do not apply colorful palette",
    )

    args = parser.parse_args()

    DEVICE = (
        "cuda"
        if torch.cuda.is_available()
        else "mps" if torch.backends.mps.is_available() else "cpu"
    )

    model_configs = {
        "vits": {
            "encoder": "vits",
            "features": 64,
            "out_channels": [48, 96, 192, 384],
        },
        "vitb": {
            "encoder": "vitb",
            "features": 128,
            "out_channels": [96, 192, 384, 768],
        },
        "vitl": {
            "encoder": "vitl",
            "features": 256,
            "out_channels": [256, 512, 1024, 1024],
        },
        "vitg": {
            "encoder": "vitg",
            "features": 384,
            "out_channels": [1536, 1536, 1536, 1536],
        },
    }

    depth_anything = DepthAnythingV2(
        **{
            **model_configs[args.encoder],
            "max_depth": args.max_depth,
        }
    )

    # Load checkpoint and fix state dict keys
    checkpoint = torch.load(args.load_from, map_location="cpu")
    if "state_dict" in checkpoint:
        print("Getting state dict from checkpoint['state_dict']")
        state_dict = checkpoint["state_dict"]

        # Fix the key prefixes
        new_state_dict = {}
        for key, value in state_dict.items():
            if key.startswith("model."):
                # Remove the "model." prefix
                new_key = key[6:]  # Skip first 6 characters ("model.")
                new_state_dict[new_key] = value
            else:
                new_state_dict[key] = value

        state_dict = new_state_dict
        depth_anything.load_state_dict(state_dict)

    else:
        depth_anything.load_state_dict(checkpoint)

    depth_anything = depth_anything.to(DEVICE).eval()

    filenames = []
    if os.path.isfile(args.img_path):
        if args.img_path.endswith("txt"):
            with open(args.img_path, "r") as f:
                filenames = f.read().splitlines()
        else:
            # Single image processing
            filenames = [args.img_path]
            if args.outdir is None:
                args.outdir = str(Path(args.img_path).parent)
    elif args.ds_type == "simcol":
        # SimCol dataset processing
        base_dir = Path(args.img_path)
        for suffix in ["I", "II", "III"]:
            pattern = f"SyntheticColon_{suffix}/Frames_*/FrameBuffer_*.png"
            filenames.extend(
                sorted(
                    glob.glob(
                        str(base_dir / pattern),
                        recursive=True,
                    )
                )
            )
        if args.outdir is None:
            args.outdir = str(base_dir)

    elif args.ds_type == "testing":
        base_dir = Path(args.img_path)
        pattern = "frame_*.jpg"
        filenames.extend(
            glob.glob(
                str(base_dir / pattern),
                recursive=True,
            )
        )
        if args.outdir is None:
            args.outdir = str(base_dir)

    # Create base output directory
    os.makedirs(args.outdir, exist_ok=True)

    cmap = matplotlib.colormaps.get_cmap("Spectral")

    skipped = 0
    for filename in tqdm(
        filenames,
        desc="Processing images",
        unit="image",
    ):

        output_folder = Path(args.outdir)
        base_name = Path(filename).stem

        if os.path.isfile(args.img_path):
            # Single image - save directly in outdir
            base_name = Path(filename).stem
            output_folder = Path(args.outdir)

        elif args.ds_type == "simcol":
            # SimCol dataset - maintain directory structure but with _OP suffix
            rel_path = Path(filename).relative_to(Path(args.img_path))
            parent_folder = rel_path.parent  # e.g., "SyntheticColon_X
            frames_dir = parent_folder.name  # e.g., "Frames_X"
            output_folder = (
                Path(args.img_path) / parent_folder.parent / f"{frames_dir}_OP"
            )
            base_name = Path(filename).stem

        elif args.ds_type == "testing":
            rel_path = Path(filename).relative_to(Path(args.img_path))
            output_folder = Path(args.outdir) / rel_path.parent
            base_name = Path(filename).stem

        # Check if files already exist
        npy_path = output_folder / f"{base_name}.npy"
        png_path = output_folder / f"{base_name}.png"

        if png_path.exists():
            skipped += 1
            continue

        # Process image only if files don't exist
        raw_image = cv2.imread(filename)
        depth = depth_anything.infer_image(raw_image, args.input_size)

        output_folder.mkdir(parents=True, exist_ok=True)

        # Save raw depth in meters
        if args.save_numpy:
            np.save(str(npy_path), depth)

        depth = (depth - depth.min()) / (depth.max() - depth.min()) * 255.0  # Normalize
        depth = depth.astype(np.uint8)  # Convert to uint8

        if args.grayscale:  # Grayscale
            depth = np.repeat(depth[..., np.newaxis], 3, axis=-1)
        else:  # Colorful
            depth = (cmap(depth)[:, :, :3] * 255)[:, :, ::-1].astype(np.uint8)

        if args.pred_only:  # Prediction only
            cv2.imwrite(str(png_path), depth)
        else:  # Display raw image and depth map side by side
            split_region = (
                np.ones(
                    (raw_image.shape[0], 50, 3),
                    dtype=np.uint8,
                )
                * 255
            )
            combined_result = cv2.hconcat([raw_image, split_region, depth])

            cv2.imwrite(str(png_path), combined_result)

    print("\nProcessing complete:")
    print(f"- Total files: {len(filenames)}")
    print(f"- Skipped existing: {skipped}")
    print(f"- Newly processed: {len(filenames) - skipped}")


# Test videos: python run.py --encoder vitl --load-from "/home/public/avaishna/Endoscopy-3D-Modeling/checkpoints/simcol/mvitl_el5e-06_dl5e-05_b6_e30_dsimcol_p0.05/depth_any_endoscopy_epoch=29_val_loss=0.02.ckpt" --max-depth 20 -i convert/test_video/colonoscopy_videos/20220107_160140_01_c -o convert/test_video/colonoscopy_videos/20220107_160140_01_c_OP -d testing
# Simcol: python run.py --encoder vitl --load-from "/home/public/avaishna/Endoscopy-3D-Modeling/checkpoints/simcol/mvitl_el5e-06_dl5e-05_b6_e30_dsimcol_p0.05/depth_any_endoscopy_epoch=29_val_loss=0.02.ckpt" --max-depth 20 -i datasets/SyntheticColon -d testing --pred-only --grayscale

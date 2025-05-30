"Module for the custom dataset"

import os
import glob

from torch.utils import data
from torchvision import transforms
import cv2
import numpy as np
import lightning as pl


class C3VDDataset(data.Dataset):
    """
    Dataset class for the C3VD dataset

    Args:
        data_dir (str): Path to the dataset directory.
        data_list (str): Path to the list of data.
        size (int): Size of the image.
        hflip (bool): Horizontal flip.
        vflip (bool): Vertical flip.
        mode (str): Mode of the dataset. Can be 'Train', 'Val', or 'Test'.
        ds_type (str): Type of the dataset.
    """

    def __init__(
        self,
        data_dir: str,
        data_list: str,
        size: int,
        mode: str,
        ds_type: str,
    ) -> None:
        self.data_dir = data_dir
        self.size = size
        self.mode = mode
        self.ds_type = ds_type

        if self.mode in (
            "Train",
            "Val",
            "Test",
        ):
            with open(data_list, "r", encoding="utf-8") as f:
                content = f.read().strip()
                folders = [folder.strip() for folder in content.split(",")]

            self.images = []
            self.depths = []

            for folder in folders:
                if not folder:  # Skip empty strings
                    continue
                folder_path = os.path.join(self.data_dir, folder)

                if not os.path.exists(folder_path):
                    print(f"Warning: Folder does not exist: {folder_path}")
                    continue

                # Get all color images (both patterns)
                color_images = sorted(
                    glob.glob(
                        os.path.join(
                            folder_path,
                            "*_color.png",
                        )
                    )
                )
                color_images.extend(
                    sorted(
                        glob.glob(
                            os.path.join(
                                folder_path,
                                "[0-9]*_*.png",
                            )
                        )
                    )
                )

                # Get corresponding depth images
                valid_pairs = []
                valid_depths = []
                for img_path in color_images:
                    # Extract the base number from the filename
                    base_num = os.path.basename(img_path).split("_")[0]

                    # Try different possible depth filename patterns
                    depth_patterns = [
                        f"{base_num}_depth.tiff",  # original number
                        f"{int(base_num):04d}_depth.tiff",  # zero-padded to 4 digits
                    ]

                    depth_file = None
                    for pattern in depth_patterns:
                        candidate_path = os.path.join(
                            os.path.dirname(img_path), pattern
                        )
                        if os.path.exists(candidate_path):
                            depth_file = candidate_path
                            break

                    if depth_file:
                        valid_pairs.append(img_path)
                        valid_depths.append(depth_file)
                    else:
                        print(f"Warning: Missing depth file for {img_path}")

                self.images.extend(valid_pairs)
                self.depths.extend(valid_depths)

            assert len(self.images) == len(
                self.depths
            ), f"Mismatch in number of images and depths for {mode} set"

        else:
            raise ValueError("Mode must be one of: 'Train', 'Val', 'Test'")

        if self.mode == "Train":
            self.transform_input = transforms.Compose(
                [
                    transforms.ToTensor(),
                    transforms.Resize(
                        (self.size, self.size),
                        interpolation=transforms.InterpolationMode.BICUBIC,
                        antialias=True,
                    ),
                    transforms.RandomHorizontalFlip(),
                    transforms.ColorJitter(
                        hue=0.2,
                        contrast=0.2,
                        brightness=0.2,
                        saturation=0.1,
                    ),
                    transforms.RandomAffine(
                        degrees=0,
                        translate=(0.1, 0.1),
                        scale=(0.1, 0.9),
                    ),
                    transforms.Normalize(
                        mean=[0.485, 0.456, 0.406],
                        std=[0.229, 0.224, 0.225],
                        # mean=[0.646, 0.557, 0.473],
                        # std=[0.055, 0.046, 0.029],
                    ),
                ]
            )
        else:
            self.transform_input = transforms.Compose(
                [
                    transforms.ToTensor(),
                    transforms.Resize(
                        (self.size, self.size),
                        interpolation=transforms.InterpolationMode.BICUBIC,
                        antialias=True,
                    ),
                    transforms.Normalize(
                        mean=[0.485, 0.456, 0.406],
                        std=[0.229, 0.224, 0.225],
                        # mean=[0.646, 0.557, 0.473],
                        # std=[0.055, 0.046, 0.029],
                    ),
                ]
            )

        self.transform_output = transforms.Compose(
            [
                transforms.ToTensor(),
                transforms.Resize(
                    (self.size, self.size),
                    interpolation=transforms.InterpolationMode.BICUBIC,
                    antialias=True,
                ),
                # transforms.Normalize(
                #     mean=[0.28444117],
                #     std=[0.2079102],
                # ),  # Single channel normalization
            ]
        )

    def __len__(self) -> int:
        return len(self.images)

    def __getitem__(self, idx) -> dict:
        info = self.images[idx].split(os.path.sep)
        dataset, frame_id = info[-3], info[-1].split(".")[0]

        image = cv2.imread(self.images[idx], cv2.IMREAD_UNCHANGED)
        depth = cv2.imread(self.depths[idx], cv2.IMREAD_UNCHANGED)

        # Read image and normalize
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        if image.dtype == np.uint16:
            # Convert np.uint16 to np.uint8
            image = (image / 256).astype("uint8")
        image = image.astype(np.float32) / 255.0

        depth = depth.astype(np.float32) / 65535.0

        image = self.transform_input(image)
        depth = self.transform_output(depth)

        return {
            "dataset": dataset,
            "id": frame_id,
            "image": image.contiguous(),
            "depth": depth.contiguous(),
            "ds_type": self.ds_type,
        }


class C3VDDataModule(pl.LightningDataModule):
    """
    Data module for the C3VD dataset

    Args:
        data_dir (str): Path to the dataset directory.
        train_list (str): Path to the training list.
        val_list (str): Path to the validation list.
        test_list (str): Path to the test list.
        batch_size (int): Batch size.
        num_workers (int): Number of workers.
        size (int): Size of the image.
    """

    def __init__(
        self,
        data_dir: str,
        train_list: str,
        val_list: str,
        test_list: str,
        ds_type: str,
        batch_size: int = 32,
        num_workers: int = 8,
        size: int = 518,
    ) -> None:
        super(C3VDDataModule, self).__init__()
        self.data_dir = data_dir
        self.train_list = train_list
        self.val_list = val_list
        self.test_list = test_list

        # Common parameters
        self.batch_size = batch_size
        self.num_workers = num_workers
        self.size = size
        self.ds_type = ds_type

        # Initialize dataset attributes
        self.train_dataset = None
        self.val_dataset = None
        self.test_dataset = None

    def prepare_data(self) -> None:
        # This method is called only once and on 1 GPU
        pass

    def setup(
        self,
        stage: str | None = None,
    ) -> None:
        """
        Setup the dataset for the given stage.

        Args:
            stage (str | None, optional): Stage of the dataset. Can be 'fit',
            'test', or None. Defaults to None.
        """
        if stage == "fit" or stage is None:
            self.train_dataset = C3VDDataset(
                data_dir=self.data_dir,
                data_list=self.train_list,
                mode="Train",
                size=self.size,
                ds_type=self.ds_type,
            )
            self.val_dataset = C3VDDataset(
                data_dir=self.data_dir,
                data_list=self.val_list,
                mode="Val",
                size=self.size,
                ds_type=self.ds_type,
            )
            if self.ds_type == "c3vd":
                print(f"C3VD Train: {len(self.train_dataset)}")
                print(f"C3VD Val:   {len(self.val_dataset)}")

        if stage == "test" or stage is None:
            self.test_dataset = C3VDDataset(
                data_dir=self.data_dir,
                data_list=self.test_list,
                mode="Test",
                size=self.size,
                ds_type=self.ds_type,
            )

            if self.ds_type == "c3vd":
                print(f"C3VD Test:  {len(self.test_dataset)}\n")

    def train_dataloader(self):
        return data.DataLoader(
            self.train_dataset,
            batch_size=self.batch_size,
            shuffle=True,
            num_workers=self.num_workers,
            pin_memory=True,
            persistent_workers=True,
            drop_last=True,
        )

    def val_dataloader(self):
        return data.DataLoader(
            self.val_dataset,
            batch_size=self.batch_size,
            shuffle=False,
            num_workers=self.num_workers,
            pin_memory=True,
            persistent_workers=True,
            drop_last=False,
        )

    def test_dataloader(self):
        return data.DataLoader(
            self.test_dataset,
            batch_size=self.batch_size,
            shuffle=False,
            num_workers=self.num_workers,
            pin_memory=True,
            persistent_workers=True,
            drop_last=False,
        )

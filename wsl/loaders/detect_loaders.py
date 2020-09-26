import sys
import numpy as np
import pandas as pd
from ast import literal_eval
import pydicom
import skimage.io
from pathlib import Path

from monai.data import Dataset
from monai.transforms import (
    Compose,
    RepeatChannel,
    Resize,
    CastToType,
    ToTensor
)
import torch
from wsl.locations import wsl_data_dir, wsl_csv_dir, known_extensions

class Loader(Dataset):
    def __init__(self, data: str, split: str, extension: str,
                 classes: int, column: str, debug: bool = False):
        self.datapath = wsl_data_dir / data
        self.data = data
        self.classes = classes
        self.column = column

        if data in known_extensions.keys():
            self.extension = known_extensions[data]
        else:
            self.extension = extension

        df = pd.read_csv(wsl_csv_dir / data / 'info.csv', converters={column: literal_eval, 'box': literal_eval})
        self.df = df
        Ids = pd.read_csv(wsl_csv_dir / data / f'{split}.csv').Id.tolist()
        df = df[df.Id.isin(Ids)]
        self.max_boxes = df['Id'].value_counts().max()
        self.names = list(set(df.Id.to_list()))
        if debug:
            self.names = self.names[0:100]

        self.image_transforms = Compose([
            Resize((224, 224)),
            RepeatChannel(repeats=3),
            CastToType(dtype=np.float32),
            ToTensor()])
        
    def load_image(self, path: Path):
        if self.extension == 'dcm':
            ref = pydicom.dcmread(path)
            img = ref.pixel_array
            pi = ref.PhotometricInterpretation
            if pi.strip() == 'MONOCHROME1':
                img = -img
        else:
            img = skimage.io.imread(path, as_gray=True)

        img = (img - np.min(img)) / (np.max(img) - np.min(img))
        img = np.expand_dims(img, axis=0)

        return img.astype(np.float32)
    
    def load_boxes(self, name: str, size: float):
        boxes = self.df[self.df == name].box.to_list()
        boxes += [-1, -1, -1, -1] * (self.max_boxes - len(boxes))
        boxes = torch.Tensor(boxes)
        boxes = boxes * 224 / size
        
        labels = self.df[self.df == name][self.column].to_list()
        labels += [0] * (self.max_boxes - len(boxes))
        labels = torch.Tensor(labels) - 1
        
        boxes = torch.cat(boxes, labels, dim=1)
        return boxes
    
    def __getitem__(self, idx):
        name = self.names[idx]
        path = self.datapath / f'{name}.{self.extension}'

        img = self.load_image(path)
        size = img.shape.mean()
        img = self.image_transforms(img)
        
        boxes = self.load_boxes(name, size)
        print(boxes)

        return img, boxes

    def __len__(self):
        return len(self.names)

import torchvision
import torchvision.datasets as dset
import torchvision.transforms as transforms
import torch
from torch.utils.data import DataLoader,Dataset
import random
import os
from PIL import Image
import matplotlib.pyplot as plt
import numpy as np
from torch.utils.data.sampler import Sampler

def imshow(img):
    npimg = img.numpy()
    plt.axis("off")
    plt.imshow(np.transpose(npimg,(1,2,0)))
    plt.show()

class Rotate(object):
    def __init__(self, angle):
        self.angle = angle
    def __call__(self, x, mode="reflect"):
        x = x.rotate(self.angle)
        return x

def omniglot_character_folders():   
    '''返回训练集及测试集字符文件夹
    num_train = 1200
    datas/omnglot_resized---|
                             |
           (family)Alphabet_of_the_Magi---|
                             |            |
                             |(character)character01---|
                             |            |            | 
                             |            |        0709_01.png
                             |            |            | 
                             |            |            ...   
                             |            |            |   
                             |           ...       0709_20.png 
                             |            |  
                            ...          character20   
                             |
                        (50)ULOG
    '''
    
    data_folder ='/home/zh510/贾霄/omniglot_resized'  
    character_folders = [os.path.join(data_folder, family, character) \
                for family in os.listdir(data_folder) \
                if os.path.isdir(os.path.join(data_folder, family)) \
                for character in os.listdir(os.path.join(data_folder, family))]
    random.seed(1)
    random.shuffle(character_folders)

    num_train = 1200
    metatrain_character_folders = character_folders[:num_train]
    metaval_character_folders = character_folders[num_train:]

    return metatrain_character_folders,metaval_character_folders

class OmniglotTask(object):  
    '''参数训练task或测试task
    每一个task都有自己的训练集和测试集，
    在Meta-learning中之前学习的task称为meta-training task，
    新的task称为meta-testing task，task内部的训练集和测试集一般称为support set和query set
    This class is for task generation for both meta training and meta testing.
    For meta training, we use all 20 samples without valid set (empty here).

    For meta testing, we use 1 or 5 shot samples for training, 
    while using the same number of samples for validation.

    If set num_samples = 20 and chracter_folders = metatrain_character_folders, 
        we generate tasks for meta training

    If set num_samples = 1 or 5 and chracter_folders = metatest_chracter_folders, 
        we generate tasks for meta testing
    '''
    def __init__(self, character_folders, num_classes, train_num,test_num):
 
        self.character_folders = character_folders
  
        self.num_classes = num_classes
      
        self.train_num = train_num
      
        self.test_num = test_num

        class_folders = random.sample(self.character_folders,self.num_classes)  
        labels = np.array(range(len(class_folders)))
        labels = dict(zip(class_folders, labels))
        '''
        labels={'C:/datas/omniglot_resized/Alphabet_of_the_Magi/character01':0,...}
        '''
        samples = dict()
        '''
        samples={'类标名':该类标对应的图片文件名}
        '''

        self.train_roots = []
        self.test_roots = []

        for c in class_folders:

            temp = [os.path.join(c, x) for x in os.listdir(c)] 

            samples[c] = random.sample(temp, len(temp))  
            '''c类标训练图片加到训练集中
                self.train_roots =['C:\datas\omniglot_resized\Alphabet_of_the_Magi\character01\0709_01.png']
                每个类标train_num个图像文件，即C-way K-shot 中的k
            '''
            self.train_roots += samples[c][:train_num]

            '''c类标训练图片加到测试集中
                self.test_roots =['C:\datas\omniglot_resized\Alphabet_of_the_Magi\character01\0709_01.png']
                每个类标query个图像文件，即C-way K-shot 中的 query数量
            '''
            self.test_roots += samples[c][train_num:train_num+test_num]  

        '''
        labels={'C:/datas/omniglot_resized/Alphabet_of_the_Magi/character01':0,...}
        '''

        self.train_labels = [labels['/'+self.get_class(x)] for x in self.train_roots]

        self.test_labels = [labels['/'+self.get_class(x)] for x in self.test_roots]

 
    def get_class(self, sample):
        #print(sample.split('\\'))
        return os.path.join(*sample.split('/')[:-1])


class FewShotDataset(Dataset):   

    def __init__(self, task, split='train', transform=None, target_transform=None):
        self.transform = transform # Torch operations on the input image
        self.target_transform = target_transform
        self.task = task
        self.split = split
        self.image_roots = self.task.train_roots if self.split == 'train' else self.task.test_roots
        self.labels = self.task.train_labels if self.split == 'train' else self.task.test_labels

    def __len__(self):
        return len(self.image_roots)

    def __getitem__(self, idx):
        raise NotImplementedError("This is an abstract class. Subclass this class for your particular dataset.")

class Omniglot(FewShotDataset):   

    def __init__(self, *args, **kwargs):
        super(Omniglot, self).__init__(*args, **kwargs)

    def __getitem__(self, idx):
        image_root = self.image_roots[idx]
        image = Image.open(image_root)
        image = image.convert('L')
        image = image.resize((28,28), resample=Image.LANCZOS) # per Chelsea's implementation
        #image = np.array(image, dtype=np.float32)
        if self.transform is not None:
            image = self.transform(image)
        label = self.labels[idx]
        if self.target_transform is not None:
            label = self.target_transform(label)  
        return image, label

class ClassBalancedSampler(Sampler):  
    ''' Samples 'num_inst' examples each from 'num_cl' pools
        of examples of size 'num_per_class' '''

    def __init__(self, num_per_class, num_cl, num_inst,shuffle=True):

        self.num_per_class = num_per_class
        self.num_cl = num_cl
        self.num_inst = num_inst
        self.shuffle = shuffle

    def __iter__(self):
        # return a single list of indices, assuming that items will be grouped by class
        if self.shuffle:
                      
            batch = [[i+j*self.num_inst for i in torch.randperm(self.num_inst)[:self.num_per_class]] for j in range(self.num_cl)]
        else:
            batch = [[i+j*self.num_inst for i in range(self.num_inst)[:self.num_per_class]] for j in range(self.num_cl)]
        batch = [item for sublist in batch for item in sublist]

        if self.shuffle:
            random.shuffle(batch)
        return iter(batch)

    def __len__(self):
        return 1


def get_data_loader(task, num_per_class=1, split='train',shuffle=True,rotation=0):
    # NOTE: batch size here is # instances PER CLASS
    #normalize = transforms.Normalize(mean=[0.92206, 0.92206, 0.92206], std=[0.08426, 0.08426, 0.08426])
    normalize = transforms.Normalize(mean=[0.92206], std=[0.08426]) 

    dataset = Omniglot(task,split=split,transform=transforms.Compose([Rotate(rotation),transforms.ToTensor(),normalize]))

    if split == 'train':

        sampler = ClassBalancedSampler(num_per_class, task.num_classes, task.train_num,shuffle=shuffle)
    else:
 
        sampler = ClassBalancedSampler(num_per_class, task.num_classes, task.test_num,shuffle=shuffle)
    loader = DataLoader(dataset, batch_size=num_per_class*task.num_classes, sampler=sampler)

    return loader


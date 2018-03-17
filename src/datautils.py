#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2018/3/7 上午9:03
# @Author  : yizhen
# @Site    : 
# @File    : datautils.py
# @Software: PyCharm

import codecs
import os
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import optim
from torch.autograd import Variable
from torch.nn.utils.rnn import pack_padded_sequence


use_cuda = torch.cuda.is_available()


def process(path):
    '''

    :param path:
    :return: x [sentence_1, sentence_2......, sentence_n], y[index_1, index_2....., index_n]
    '''
    data_x, data_y = [], []
    with codecs.open(path, 'r', encoding='utf-8') as fp:
        fp_content = fp.read().strip().split('\n')
        for instance_index, instance in enumerate(fp_content):
            instance_x = instance[6:]
            instance_y = instance[0]
            data_x.append(instance_x)
            data_y.append(instance_y)

    return data_x, data_y


def preprocess(path):
    '''

    :param path: path_dir
    :return: train_x, train_y, valid_x, valid_y, test_x, test_y: format list[]
    '''
    train_path = os.path.join(path, 'train.txt')
    valid_path = os.path.join(path, 'valid.txt')
    test_path = os.path.join(path, 'test.txt')

    train_x, train_y = process(train_path)
    valid_x, valid_y = process(valid_path)
    test_x, test_y = process(test_path)

    return train_x, train_y, valid_x, valid_y, test_x, test_y


def collate_batch(batch):
    outputs_instances = []
    outputs_lables = []
    for key in batch:
        outputs_instances.append(key[0])
        outputs_lables.append(key[1])
    return outputs_instances, outputs_lables


def padding(instance_x, instance_y):
    '''
    return padded data
    :param instance_x:  []
    :param instance_y:  []
    :return:
    '''
    # lst = sorted(lst, lambda )
    lst = range(len(instance_x))
    lst = sorted(lst, key=lambda d: -len(instance_x[d]))
    instance_x = [instance_x[index] for index in lst]  # be sorted in decreasing order for packed
    instance_y = [instance_y[index] for index in lst]

    sentence_lens = [len(sentence) for sentence in instance_x]  # for pack-padded deal

    max_len = max(len(sentence) for sentence in instance_x)
    instance_x = [sentence + (max_len - len(sentence)) * [0] for sentence in instance_x]

    return instance_x, instance_y, sentence_lens


class Lang:
    def __init__(self):
        self.word2idx = {'PAD': 0, 'OOV': 1}
        self.idx2word = {}
        self.word_size = 2

    def add_word(self, word):
        '''
        add word to dict
        :param word:
        :return:
        '''
        if word not in self.word2idx:
            self.word2idx[word] = len(self.word2idx)
            self.word_size += 1
            self.idx2word = self.get_idx_to_word()

    def add_sentence(self, sentence):
        '''
        add sentence to dict
        :param sentence:
        :return:
        '''
        for word in sentence.strip().split():
            self.add_word(word)

    def get_idx_to_word(self):
        '''
        get idx_to_word
        :return:
        '''
        self.idx2word = {idx: word for word, idx in self.word2idx.items()}
        return self.idx2word

    def sentence_to_idx(self, sentence):
        '''
        '''
        return [self.word2idx.get(word, 1) for word in sentence.split()]

    def get_word_size(self):
        '''

        :return: word_size
        '''
        return self.word_size

    def sentence_to_idx2(self, instance_x, instance_y):
        '''

        :param lang:
        :param instance_x:[]
        :param instance_y:[]
        :return: instance_x_idx, instance_y_idx
        '''
        instance_x_idx, instance_y_idx = [], []

        for sentence_index, sentence in enumerate(instance_x):
            instance_x_idx.append(self.sentence_to_idx(sentence))

        for index_y, y in enumerate(instance_y):
            instance_y_idx.append(int(y))

        return instance_x_idx, instance_y_idx

    def generate_dict(self, data):
        '''
        :param: lang
        :param： data
        :return: lang after add dict
        '''

        for instance_index, instance in enumerate(data):
            self.add_sentence(instance)


def get_batch(instance_x, instance_y, batch_size, batch_lst):
    '''
    # here, we get the padding。
    :param instance_x: [sentence_1, sentence_2,,,,,]
    :param instance_y: [gold_1, gold_2,,,,,]
    :param batch_size:[] batch_size
    :param batch_lst [] batch_lst ,batch的lst序号
    :return:
    '''
    batch_instance_x = [instance_x[index] for index in batch_lst]
    batch_instance_y = [instance_y[index] for index in batch_lst]
    max_length = max([len(sentence) for sentence in batch_instance_x])

    # padding
    batch_instance_x_padding = [[sentence + (max_length - len(sentence)) * [0]] for sentence in batch_instance_x]
    if use_cuda:
        batch_instance_x_padding = Variable(torch.LongTensor(batch_instance_x_padding)).cuda()
        batch_instance_y = Variable(torch.LongTensor(batch_instance_y)).cuda()
    else:
        batch_instance_x_padding = Variable(torch.LongTensor(batch_instance_x_padding))
        batch_instance_y = Variable(torch.LongTensor(batch_instance_y))

    return batch_instance_x_padding, batch_instance_y




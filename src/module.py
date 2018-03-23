#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Time    : 2018/3/7 下午12:28
# @Author  : yizhen
# @Site    :
# @File    : module.py
# @Software: PyCharm

import torch
from torch.nn.parameter import Parameter
import torch.nn as nn
from datautils import padding, padding_word_char
import torch.nn.functional as F
from torch import optim
import numpy as np
import random

from torch.autograd import Variable
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence


class Model(nn.Module):
    def __init__(self, data):
        super(Model, self).__init__()
        self.input_size = data.input_size
        self.hidden_size = data.HP_hidden_dim
        self.output_size = data.label_alphabet_size
        self.vocal_size = data.word_alphabet_size
        self.embedding_size = data.HP_word_emb_dim
        self.NLLoss = nn.NLLLoss()
        self.dropout = nn.Dropout(data.HP_dropout)
        self.softmax = nn.LogSoftmax()
        self.use_cuda = data.HP_gpu
        self.embedding = nn.Embedding(self.vocal_size, self.embedding_size)
        self.dropout_rate = data.HP_dropout
        self.seed = data.HP_seed
        self.use_char = data.HP_use_char
        print "data.HP_use_char"
        print data.HP_use_char
        torch.manual_seed(self.seed)  # fixed the seed
        random.seed(self.seed)

        if data.pretrain_word_embedding is not None:
            self.embedding.weight = nn.Parameter(torch.FloatTensor(data.pretrain_word_embedding))

        if self.use_char:
            self.char_feature = CharBiLSTM(self.use_cuda, data.char_alphabet_size, data.HP_char_emb_dim,
                                           data.HP_char_hidden_dim, data.HP_char_dropout, data.pretrain_char_embedding)


class LstmModel(Model):
    def __init__(self, data):
        super(LstmModel, self).__init__(data)

        self.linear = nn.Linear(self.hidden_size, self.output_size)

        self.lstm = nn.LSTM(input_size=self.input_size,
                            hidden_size=self.hidden_size,
                            batch_first=True,
                            dropout=self.dropout_rate)

        self.w_i_in, self.w_i_on = self.lstm.all_weights[0][0].size()
        self.w_h_in, self.w_h_on = self.lstm.all_weights[0][1].size()
        self.lstm.all_weights[0][0] = Parameter(torch.randn(self.w_i_in, self.w_i_on)) * np.sqrt(2. / self.w_i_on)
        self.lstm.all_weights[0][1] = Parameter(torch.randn(self.w_h_in, self.w_h_on)) * np.sqrt(2. / self.w_h_on)

    def forward(self, input_x, input_char, input_y):
        """
        intput_x: b_s instances， 没有进行padding和Variable
        :param input:
        :return:
        """

        word_seq_tensor, word_seq_lengths, word_seq_recover, char_seq_tensor, char_seq_lengths, char_seq_recover, label_seq_tensor, mask = padding_word_char(
            self.use_cuda, input_x, input_char, input_y)

        input_x = word_seq_tensor
        input_y = label_seq_tensor

        embed_input_x = self.embedding(input_x)  # embed_intput_x: (b_s, m_l, em_s)

        batch_size = word_seq_tensor.size(0)
        sent_len = word_seq_tensor.size(1)

        if self.use_char:
            char_features = self.char_feature.get_last_hiddens(char_seq_tensor,
                                                               char_seq_lengths.numpy())  # Variable(batch_size, char_hidden_dim)
            char_features = char_features[char_seq_recover]
            char_features = char_features.view(batch_size, sent_len, -1)
            embed_input_x = torch.cat([embed_input_x, char_features], 2)

        embed_input_x = self.dropout(embed_input_x)

        embed_input_x_packed = pack_padded_sequence(embed_input_x, word_seq_lengths.numpy(), batch_first=True)
        encoder_outputs_packed, (h_last, c_last) = self.lstm(embed_input_x_packed)
        encoder_outputs, _ = pad_packed_sequence(encoder_outputs_packed, batch_first=True)

        predict = self.linear(h_last)  # predict: [test.txt, b_s, o_s]
        predict = self.softmax(predict.squeeze(0))  # predict.squeeze(0) [b_s, o_s]

        loss = self.NLLoss(predict, input_y)

        if self.training:  # if it is in training module
            return loss
        else:
            value, index = torch.max(predict, 1)
            return index  # outsize, cal the acc


class BilstmModel(Model):
    def __init__(self, data):
        super(BilstmModel, self).__init__(data)

        self.linear = nn.Linear(self.hidden_size * 2, self.output_size)
        self.lstm = nn.LSTM(input_size=self.input_size,
                            hidden_size=self.hidden_size,
                            batch_first=True,
                            dropout=self.dropout_rate,
                            bidirectional=True)

    def forward(self, input_x, input_char, input_y):
        """
        intput_x: b_s instances， 没有进行padding和Variable
        :param input_y:
        :param input_char:
        :param input_x:
        :return:
        """
        # input_x, batch_chars, input_y, sentence_lens, word_lens = padding(input_x, input_char, input_y)
        word_seq_tensor, word_seq_lengths, word_seq_recover, char_seq_tensor, char_seq_lengths, char_seq_recover, label_seq_tensor, mask = padding_word_char(
            self.use_cuda, input_x, input_char, input_y)

        input_x = word_seq_tensor
        input_y = label_seq_tensor

        embed_input_x = self.embedding(input_x)  # embed_intput_x: (b_s, m_l, em_s)

        batch_size = word_seq_tensor.size(0)
        sent_len = word_seq_tensor.size(1)

        if self.use_char:
            char_features = self.char_feature.get_last_hiddens(char_seq_tensor,
                                                               char_seq_lengths.numpy())  # Variable(batch_size, char_hidden_dim)
            char_features = char_features[char_seq_recover]
            char_features = char_features.view(batch_size, sent_len, -1)
            embed_input_x = torch.cat([embed_input_x, char_features], 2)

        embed_input_x = self.dropout(embed_input_x)

        encoder_outputs, (h_last, c_last) = self.lstm(embed_input_x)
        h_last = torch.cat((h_last[0], h_last[1]), 1)

        predict = self.linear(h_last)  # predict: [test.txt, b_s, o_s]
        predict = self.softmax(predict.squeeze(0))  # predict.squeeze(0) [b_s, o_s]

        loss = self.NLLoss(predict, input_y)

        if self.training:  # if it is in training module
            return loss
        else:
            value, index = torch.max(predict, 1)
            return index  # outsize, cal the acc


class CnnModel(Model):

    def __init__(self, data):
        super(CnnModel, self).__init__(data)
        self.l2 = data.HP_l2
        self.kernel_size = [int(size) for size in data.HP_kernel_size.split("*")]
        self.kernel_num = [int(num) for num in data.HP_kernel_num.split("*")]
        nums = sum(self.kernel_num)
        self.linear = nn.Linear(nums, self.output_size)
        self.convs = nn.ModuleList(
            [nn.Conv2d(1, num, (size, self.input_size)) for (size, num) in zip(self.kernel_size, self.kernel_num)])

    def forward(self, input_x, input_char, input_y):
        word_seq_tensor, word_seq_lengths, word_seq_recover, char_seq_tensor, char_seq_lengths, char_seq_recover, label_seq_tensor, mask = padding_word_char(
            self.use_cuda, input_x, input_char, input_y)

        input_x = word_seq_tensor
        input_y = label_seq_tensor
	batch_size = word_seq_tensor.size(0)
        sent_len = word_seq_tensor.size(1)

        self.poolings = nn.ModuleList([nn.MaxPool1d(sent_len - size + 1, 1) for size in
                                       self.kernel_size])  # the output of each pooling layer is a number

	input = input_x.squeeze(1)
        embed_input_x = self.embedding(input)  # embed_intput_x: (b_s, m_l, em_s)

        if self.use_char:
            char_features = self.char_feature.get_last_hiddens(char_seq_tensor,
                                                               char_seq_lengths.numpy())  # Variable(batch_size, char_hidden_dim)
            char_features = char_features[char_seq_recover]
            char_features = char_features.view(batch_size, sent_len, -1)
            embed_input_x = torch.cat([embed_input_x, char_features], 2)

        embed_input_x = self.dropout(embed_input_x)
        embed_input_x = embed_input_x.view(embed_input_x.size(0), 1, -1, embed_input_x.size(2))

        parts = []  # example:[3,4,5] [100,100,100] the dims of data though pooling layer is 100 + 100 + 100 = 300
        for (conv, pooling) in zip(self.convs, self.poolings): 
		conved_data = conv(embed_input_x).squeeze()	
		if len(conved_data.size()) == 2:
			conved_data = conved_data.view(1,conved_data.size(0),conved_data.size(1))
		pooled_data = pooling(conved_data).view(input_x.size(0), -1)	
		parts.append(pooled_data)
        x = F.relu(torch.cat(parts, 1))

        # make sure the l2 norm of w less than l2
        w = torch.mul(self.linear.weight, self.linear.weight).sum().data[0]
        if w > self.l2 * self.l2:
            x = torch.mul(x.weight, np.math.sqrt(self.l2 * self.l2 * 1.0 / w))

        predict = self.linear(x)  # predict: [1, b_s, o_s]
        predict = self.softmax(predict.squeeze(0))  # predict.squeeze(0) [b_s, o_s]

        loss = self.NLLoss(predict, input_y)

        if self.training:  # if it is in training module
            return loss
        else:
            value, index = torch.max(predict, 1)
            return index  # outsize, cal the acc


class SumModel(Model):
    def __init__(self, data):
        super(SumModel, self).__init__(data)
        self.linear = nn.Linear(self.input_size, self.output_size)

    def forward(self, input_x, input_char, input_y):

        word_seq_tensor, word_seq_lengths, word_seq_recover, char_seq_tensor, char_seq_lengths, char_seq_recover, label_seq_tensor, mask = padding_word_char(
            self.use_cuda, input_x, input_char, input_y)

        input_x = word_seq_tensor
        input_y = label_seq_tensor

        embed_input_x = self.embedding(input_x)  # embed_intput_x: (b_s, m_l, em_s)

        batch_size = word_seq_tensor.size(0)
        sent_len = word_seq_tensor.size(1)

        if self.use_char:
            char_features = self.char_feature.get_last_hiddens(char_seq_tensor,
                                                               char_seq_lengths.numpy())  # Variable(batch_size, char_hidden_dim)
            char_features = char_features[char_seq_recover]
            char_features = char_features.view(batch_size, sent_len, -1)
            embed_input_x = torch.cat([embed_input_x, char_features], 2)

        embed_input_x = self.dropout(embed_input_x)

        encoder_outputs = torch.zeros(len(input_y), self.input_size)  # 存放加和平均的句子表示

        if self.use_cuda:
            encoder_outputs = Variable(encoder_outputs).cuda()
        else:
            encoder_outputs = Variable(encoder_outputs)

        for index, batch in enumerate(embed_input_x):
            true_batch = batch[0:word_seq_lengths[index]]  # 根据每一个句子的实际长度取出实际batch
            encoder_outputs[index] = torch.mean(true_batch, 0)  # 平均

        predict = self.linear(encoder_outputs)
        predict = self.softmax(predict)
        loss = self.NLLoss(predict, input_y)

        if self.training:  # if it is in training module
            return loss
        else:
            value, index = torch.max(predict, 1)
            return index  # outsize, cal the acc


class CharBiLSTM(nn.Module):
    def __init__(self, use_cuda, alphabet_size, embedding_dim, hidden_dim, dropout_rate, pretrined_embedding=None):
        super(CharBiLSTM, self).__init__()
        self.use_cuda = use_cuda
        self.alphabet_size = alphabet_size
        self.embedding_dim = embedding_dim
        self.hidden_dim = hidden_dim
        self.dropout_rate = dropout_rate
        self.char_drop = nn.Dropout(self.dropout_rate)
        self.char_embeddings = nn.Embedding(alphabet_size, embedding_dim)

        if pretrined_embedding is not None:
            self.char_embeddings.weight = nn.Parameter(torch.FloatTensor(pretrined_embedding))

        self.char_lstm = nn.LSTM(embedding_dim, self.hidden_dim, num_layers=1, batch_first=True,
                                 bidirectional=True)

        if self.use_cuda:
            self.char_drop = self.char_drop.cuda()
            self.char_embeddings = self.char_embeddings.cuda()
            self.char_lstm = self.char_lstm.cuda()

    def get_last_hiddens(self, input, seq_lengths):
        """
            input:
                input: Variable(batch_size, word_length)
                seq_lengths: numpy array (batch_size,  1)
            output:
                Variable(batch_size, char_hidden_dim)
            Note it only accepts ordered (length) variable, length size is recorded in seq_lengths
        """
        batch_size = input.size(0)
        char_embeds = self.char_drop(self.char_embeddings(input))
        char_hidden = None
        pack_input = pack_padded_sequence(char_embeds, seq_lengths, True)
        char_rnn_out, char_hidden = self.char_lstm(pack_input, char_hidden)
        char_rnn_out, _ = pad_packed_sequence(char_rnn_out)
        return char_hidden[0].transpose(1, 0).contiguous().view(batch_size, -1)

    def get_all_hiddens(self, input, seq_lengths):
        """
            input:
                input: Variable(batch_size,  word_length)
                seq_lengths: numpy array (batch_size,  1)
            output:
                Variable(batch_size, word_length, char_hidden_dim)
            Note it only accepts ordered (length) variable, length size is recorded in seq_lengths
        """
        batch_size = input.size(0)
        char_embeds = self.char_drop(self.char_embeddings(input))
        char_hidden = None
        pack_input = pack_padded_sequence(char_embeds, seq_lengths, True)
        char_rnn_out, char_hidden = self.char_lstm(pack_input, char_hidden)
        char_rnn_out, _ = pad_packed_sequence(char_rnn_out)
        return char_rnn_out.transpose(1, 0)

    def forward(self, input, seq_lengths):
        return self.get_all_hiddens(input, seq_lengths)

import numpy as np
import theano
import sys
import csv
theano.config.on_unused_input = 'ignore'
import theano.tensor as T
import logging
from theanify import theanify, Theanifiable
logging.basicConfig(level=logging.DEBUG)
from argparse import ArgumentParser
import random
from dataset import *

from deepx.nn import *
from deepx.rnn import *
from deepx.loss import *
from deepx.optimize import *


class WindowedBatcher(object):

    def __init__(self, sequences, encodings, target, batch_size=100, sequence_length=50):
        self.sequences = sequences

        self.pre_vector_sizes = [c.seq[0].shape[0] for c in self.sequences] + [target.seq[0].shape[0]]
        self.pre_vector_size = sum(self.pre_vector_sizes)
        self.target_size = target.seq[0].shape[0]

        self.encodings = encodings
        self.vocab_sizes = [c.index for c in self.encodings] + [self.target_size]
        self.vocab_size = sum(self.vocab_sizes)
        self.batch_index = 0
        self.batches = []
        self.batch_size = batch_size
        self.sequence_length = sequence_length
        self.length = len(self.sequences[0])

        self.batch_index = 0
        self.X = np.zeros((self.length, self.pre_vector_size), dtype=np.int32)
        self.X = np.hstack([c.seq for c in self.sequences] + [target.seq])

        N, D = self.X.shape
        assert N > self.batch_size * self.sequence_length, "File has to be at least %u characters" % (self.batch_size * self.sequence_length)

        self.X = self.X[:N - N % (self.batch_size * self.sequence_length)]
        self.N, self.D = self.X.shape
        self.X = self.X.reshape((self.N / self.sequence_length, self.sequence_length, self.D))

        self.N, self.S, self.D = self.X.shape

        self.num_sequences = self.N / self.sequence_length
        self.num_batches = self.N / self.batch_size
        self.batch_cache = {}

    def next_batch(self):
        idx = (self.batch_index * self.batch_size)
        if self.batch_index >= self.num_batches:
            self.batch_index = 0
            idx = 0

        if self.batch_index in self.batch_cache:
            batch = self.batch_cache[self.batch_index]
            self.batch_index += 1
            return batch

        X = self.X[idx:idx + self.batch_size]
        y = np.zeros((X.shape[0], self.sequence_length, self.vocab_size))
        for i in xrange(self.batch_size):
            for c in xrange(self.sequence_length):
                seq_splits = np.split(X[i, c], np.cumsum(self.pre_vector_sizes))
                vec = np.concatenate([e.convert_representation(split) for
                                      e, split in zip(self.encodings, seq_splits)] + [X[i, c, -self.target_size:]])
                y[i, c] = vec

        X = y[:, :, :-self.target_size]
        y = y[:, :, -self.target_size:]


        X = np.swapaxes(X, 0, 1)
        y = np.swapaxes(y, 0, 1)
        # self.batch_cache[self.batch_index] = X, y
        self.batch_index += 1
        return X, y

def parse_args():
    argparser = ArgumentParser()

    argparser.add_argument("real_file")
    argparser.add_argument("fake_file")

    return argparser.parse_args()

def generate(length, temperature):
    results = charrnn.generate(
        np.eye(len(encoding))[encoding.encode("i")],
        length,
        temperature).argmax(axis=1)
    return NumberSequence(results).decode(encoding)


if __name__ == "__main__":
    args = parse_args()
    logging.debug("Reading file...")
    with open(args.real_file, 'r') as fp:
        real_reviews = [r[3:] for r in fp.read().strip().split('\n')]
    with open(args.fake_file, 'r') as fp:
        fake_reviews = [r[3:] for r in fp.read().strip().split('\n')]

    # Load and shuffle reviews
    real_targets, fake_targets = [],  []
    for _ in xrange(len(real_reviews)):
        real_targets.append([0, 1])
    for _ in xrange(len(fake_reviews)):
        fake_targets.append([1, 0])

    all_reviews = zip(real_reviews, real_targets) + zip(fake_reviews, fake_targets)

    random.seed(1)
    random.shuffle(all_reviews)

    # Partition training set due to memory constraints on AWS
    reviews, targets = zip(*all_reviews[:100000])
    
    logging.debug("Converting to one-hot...")
    review_sequences = [CharacterSequence.from_string(review) for review in reviews]

    text_encoding = OneHotEncoding(include_start_token=True, include_stop_token=True)
    text_encoding.build_encoding(review_sequences)

    num_sequences = [c.encode(text_encoding) for c in review_sequences]
    final_seq = NumberSequence(np.concatenate([c.seq.astype(np.int32) for c in num_sequences]))
    target_sequences = [NumberSequence([target]).replicate(len(r)) for target, r in zip(targets, num_sequences)]
    final_target = NumberSequence(np.concatenate([c.seq.astype(np.int32) for c in target_sequences]))

    # Construct the batcher
    batcher = WindowedBatcher([final_seq], [text_encoding], final_target, sequence_length=200, batch_size=100)
    
    # Define the model
    logging.debug("Compiling model")
    discriminator = Sequence(Vector(len(text_encoding))) >> MultilayerLSTM(1024, num_layers=2) >> Softmax(2)
    
    # Training
    rmsprop = RMSProp(discriminator, ConvexSequentialLoss(CrossEntropy(), 0.5), clip_gradients=5)

    step_size  = 5
    iterations = 1000

    # Training loss
    train_loss = []
    for _ in xrange(iterations):
        X, y = batcher.next_batch()
        train_loss.append(rmsprop.train(X,Y,step_size))

    # Training accuracy
    

    # Testing accuracy


    # with open('loss/loss_0.25_50.csv', 'wb') as loss_file:
    #     wr = csv.writer(loss_file)
    #     wr.writerow(loss)
    
       
    # Training Accuracy
    # test_reviews = [np.vstack([text_encoding.convert_representation(a) for a in r.encode(text_encoding).seq]) [:, np.newaxis] for r in review_sequences[:100]]
    # test_labels = np.array(targets)[:100].argmax(axis=1)
    # discriminator.compile_method('accuracy') #
    # discriminator.compile_method('predict')

    # errors = 0
    # for review, label in zip(test_reviews, test_labels):
    #     error = discriminator.accuracy(review[:, np.newaxis], np.zeros((1, 2, 1024)), [label])
    #     if error == 0:
    #         print "Correct!"
    #     errors += error

    # print "Error rate: %f" % (float(errors) / 100)


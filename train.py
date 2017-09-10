#!/usr/bin/env python3
#-------------------------------------------------------------------------------
# Author: Lukasz Janyst <lukasz@jany.st>
# Date:   07.09.2017
#-------------------------------------------------------------------------------
# This file is part of SSD-TensorFlow.
#
# SSD-TensorFlow is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SSD-TensorFlow is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SSD-Tensorflow.  If not, see <http://www.gnu.org/licenses/>.
#-------------------------------------------------------------------------------

import argparse
import math
import sys
import os

import tensorflow as tf
import numpy as np

from training_data import TrainingData
from ssdvgg import SSDVGG
from utils import *
from tqdm import tqdm

#-------------------------------------------------------------------------------
def main():
    #---------------------------------------------------------------------------
    # Parse the commandline
    #---------------------------------------------------------------------------
    parser = argparse.ArgumentParser(description='Train the SSD')
    parser.add_argument('--name', default='test',
                        help='project name')
    parser.add_argument('--data-dir', default='pascal-voc-2007',
                        help='data directory')
    parser.add_argument('--vgg-dir', default='vgg_graph',
                        help='directory for the VGG-16 model')
    parser.add_argument('--epochs', type=int, default=10,
                        help='number of training epochs')
    parser.add_argument('--batch-size', type=int, default=32,
                        help='batch size')
    parser.add_argument('--tensorboard-dir', default="tb",
                        help='name of the tensorboard data directory')
    parser.add_argument('--checkpoint-interval', type=int, default=50,
                        help='checkpoint interval')
    args = parser.parse_args()

    print('[i] Project name:         ', args.name)
    print('[i] Data directory:       ', args.data_dir)
    print('[i] VGG directory:        ', args.vgg_dir)
    print('[i] # epochs:             ', args.epochs)
    print('[i] Batch size:           ', args.batch_size)
    print('[i] Tensorboard directory:', args.tensorboard_dir)
    print('[i] Checkpoint interval:  ', args.checkpoint_interval)

    try:
        print('[i] Creating directory {}...'.format(args.name))
        os.makedirs(args.name)
    except (IOError) as e:
        print('[!]', str(e))
        return 1

    #---------------------------------------------------------------------------
    # Configure the training data
    #---------------------------------------------------------------------------
    print('[i] Configuring the training data...')
    try:
        td = TrainingData(args.data_dir)
        print('[i] # training samples:   ', td.num_train)
        print('[i] # validation samples: ', td.num_valid)
        print('[i] # classes:            ', td.num_classes)
        print('[i] Image size:           ', td.preset.image_size)
    except (AttributeError, RuntimeError) as e:
        print('[!] Unable to load training data:', str(e))
        return 1

    #---------------------------------------------------------------------------
    # Create the network
    #---------------------------------------------------------------------------
    with tf.Session() as sess:
        print('[i] Creating the model...')
        net = SSDVGG(sess)
        net.build_from_vgg(args.vgg_dir, td.num_classes, td.preset,
                           progress_hook='tqdm')

        labels = tf.placeholder(tf.float32,
                                shape=[None, None, td.num_classes+5])

        optimizer, loss = net.get_optimizer(labels)

        summary_writer  = tf.summary.FileWriter(args.tensorboard_dir,
                                                sess.graph)
        saver           = tf.train.Saver(max_to_keep=10)

        n_train_batches = int(math.ceil(td.num_train/args.batch_size))
        initialize_uninitialized_variables(sess)

        #-----------------------------------------------------------------------
        # Summaries
        #-----------------------------------------------------------------------
        validation_loss = tf.placeholder(tf.float32)
        validation_loss_summary_op = tf.summary.scalar('validation_loss',
                                                       validation_loss)

        training_loss = tf.placeholder(tf.float32)
        training_loss_summary_op = tf.summary.scalar('training_loss',
                                                     training_loss)

        print('[i] Training...')
        for e in range(args.epochs):
            #-------------------------------------------------------------------
            # Train
            #-------------------------------------------------------------------
            generator = td.train_generator(args.batch_size)
            description = '[i] Epoch {:>2}/{}'.format(e+1, args.epochs)
            training_loss_total = 0
            for x, y in tqdm(generator, total=n_train_batches,
                             desc=description, unit='batches'):
                feed = {net.image_input:  x,
                        labels:           y,
                        net.keep_prob:    1}
                loss_batch, _ = sess.run([loss, optimizer], feed_dict=feed)
                training_loss_total += loss_batch * x.shape[0]
            training_loss_total /= td.num_train

            #-------------------------------------------------------------------
            # Validate
            #-------------------------------------------------------------------
            generator = td.valid_generator(args.batch_size)
            validation_loss_total = 0

            for x, y in generator:
                feed = {net.image_input:  x,
                        labels:           y,
                        net.keep_prob:    1}
                loss_batch = sess.run(loss, feed_dict=feed)
                validation_loss_total += loss_batch * x.shape[0]

            validation_loss_total /= td.num_valid

            #-------------------------------------------------------------------
            # Write loss summary
            #-------------------------------------------------------------------
            feed = {validation_loss: validation_loss_total,
                    training_loss:   training_loss_total}
            loss_summary = sess.run([validation_loss_summary_op,
                                     training_loss_summary_op],
                                    feed_dict=feed)

            summary_writer.add_summary(loss_summary[0], e)
            summary_writer.add_summary(loss_summary[1], e)

            #-------------------------------------------------------------------
            # Save a checktpoint
            #-------------------------------------------------------------------
            if (e+1) % args.checkpoint_interval == 0:
                checkpoint = '{}/e{}.ckpt'.format(args.name, e+1)
                saver.save(sess, checkpoint)
                print('Checkpoint saved:', checkpoint)

        checkpoint = '{}/final.ckpt'.format(args.name)
        saver.save(sess, checkpoint)
        print('Checkpoint saved:', checkpoint)

    return 0

if __name__ == '__main__':
    sys.exit(main())
from __future__ import print_function
import tensorflow as tf
import numpy as np
import math
import sklearn


class Conv1DClassifier:
    def __init__(self, seq_len, vocab_size, n_out, sess=tf.Session(), embedding_dims=50, padding='valid'):
        """
        Parameters:
        -----------
        seq_len: int
            Sequence length
        vocab_size: int
            Vocabulary size
        embedding_dims: int
            Word embedding dimensions
        n_filters: int
            Number output of filters in the convolution
        kernel_size: int
            Size of the 1D convolution window
        hidden_dims: int
            Ouput dimensions of the fully-connected layer
        n_out: int
            Output dimensions
        sess: object
            tf.Session() object 
        """
        self.seq_len = seq_len
        self.vocab_size = vocab_size
        self.embedding_dims = embedding_dims
        self.padding = padding
        self.n_out = n_out
        self.sess = sess
        self._cursor = None
        self._seq_len = 0
        self.build_graph()
    # end constructor


    def build_graph(self):
        self.add_input_layer()
        self.add_word_embedding()
        self.conv1 = self.add_conv1d(250, kernel_size=3)
        self.conv2 = self.add_conv1d(250, kernel_size=4)
        self.conv3 = self.add_conv1d(250, kernel_size=5)
        self.merge_layers([self.conv1, self.conv2, self.conv3])
        self.add_global_pooling()
        self.add_output_layer()   
        self.add_backward_path()
    # end method build_graph


    def add_input_layer(self):
        self.X = tf.placeholder(tf.int32, [None, self.seq_len])
        self.Y = tf.placeholder(tf.int64, [None])
        self.keep_prob = tf.placeholder(tf.float32)
        self.lr = tf.placeholder(tf.float32)
        self._cursor = self.X
    # end method add_input_layer


    def add_word_embedding(self):
        embedding = tf.get_variable('encoder', [self.vocab_size,self.embedding_dims], tf.float32,
                                     tf.random_uniform_initializer(-1.0, 1.0))
        embedded = tf.nn.embedding_lookup(embedding, self._cursor)
        self._cursor = tf.nn.dropout(embedded, self.keep_prob)
    # end method add_word_embedding_layer


    def add_conv1d(self, n_filters, kernel_size, strides=1):
        Y = tf.layers.conv1d(inputs = self._cursor,
                             filters = n_filters,
                             kernel_size  = kernel_size,
                             strides = strides,
                             padding=self.padding,
                             use_bias = True,
                             activation = tf.nn.relu)
        if self.padding == 'valid':
            self._seq_len += int((self.seq_len - kernel_size + 1) / strides)
        if self.padding == 'same':
            self._seq_len += int(self.seq_len / strides)
        return Y
    # end method add_conv1d_layer


    def merge_layers(self, layers):
        self._cursor = tf.concat(layers, axis=1)
    # end method merge_layers


    def add_global_pooling(self):
        Y = tf.layers.average_pooling1d(inputs = self._cursor,
                                        pool_size = self._seq_len,
                                        strides = 1,
                                        padding = self.padding)
        Y = tf.reshape(Y, [-1, self.n_filters])
        self._cursor = Y
    # end method add_global_maxpool_layer


    def add_output_layer(self):
        self.logits = tf.layers.dense(self._cursor, self.n_out)
    # end method add_output_layer


    def add_backward_path(self):
        self.loss = tf.reduce_mean(tf.nn.sparse_softmax_cross_entropy_with_logits(logits=self.logits, labels=self.Y))
        self.train_op = tf.train.AdamOptimizer(self.lr).minimize(self.loss)
        self.acc = tf.reduce_mean(tf.cast(tf.equal(tf.argmax(self.logits, 1), self.Y), tf.float32))
    # end method add_backward_path


    def fit(self, X, Y, val_data=None, n_epoch=10, batch_size=128, keep_prob=1.0, en_exp_decay=True,
            en_shuffle=True):
        if val_data is None:
            print("Train %d samples" % len(X))
        else:
            print("Train %d samples | Test %d samples" % (len(X), len(val_data[0])))
        log = {'loss':[], 'acc':[], 'val_loss':[], 'val_acc':[]}
        global_step = 0

        self.sess.run(tf.global_variables_initializer()) # initialize all variables
        for epoch in range(n_epoch):
            if en_shuffle:
                X, Y = sklearn.utils.shuffle(X, Y)
            local_step = 1
            
            for X_batch, Y_batch in zip(self.gen_batch(X, batch_size),
                                        self.gen_batch(Y, batch_size)): # batch training
                lr = self.decrease_lr(en_exp_decay, global_step, n_epoch, len(X), batch_size) 
                _, loss, acc = self.sess.run([self.train_op, self.loss, self.acc],
                                             {self.X:X_batch, self.Y:Y_batch,
                                              self.lr:lr, self.keep_prob:keep_prob})
                local_step += 1
                global_step += 1
                if local_step % 50 == 0:
                    print ("Epoch %d/%d | Step %d/%d | train_loss: %.4f | train_acc: %.4f | lr: %.4f"
                        %(epoch+1, n_epoch, local_step, int(len(X)/batch_size), loss, acc, lr))

            if val_data is not None: # go through test dara, compute averaged validation loss and acc
                val_loss_list, val_acc_list = [], []
                for X_test_batch, Y_test_batch in zip(self.gen_batch(val_data[0], batch_size),
                                                      self.gen_batch(val_data[1], batch_size)):
                    v_loss, v_acc = self.sess.run([self.loss, self.acc],
                                                  {self.X:X_test_batch, self.Y:Y_test_batch,
                                                   self.keep_prob:1.0})
                    val_loss_list.append(v_loss)
                    val_acc_list.append(v_acc)
                val_loss, val_acc = self.list_avg(val_loss_list), self.list_avg(val_acc_list)

            # append to log
            log['loss'].append(loss)
            log['acc'].append(acc)
            if val_data is not None:
                log['val_loss'].append(val_loss)
                log['val_acc'].append(val_acc)
            # verbose
            if val_data is None:
                print ("Epoch %d/%d | train_loss: %.4f | train_acc: %.4f |" % (epoch+1, n_epoch, loss, acc),
                    "lr: %.4f" % (lr) )
            else:
                print ("Epoch %d/%d | train_loss: %.4f | train_acc: %.4f |" % (epoch+1, n_epoch, loss, acc),
                    "test_loss: %.4f | test_acc: %.4f |" % (val_loss, val_acc),
                    "lr: %.4f" % (lr) )
        # end "for epoch in range(n_epoch):"

        return log
    # end method fit


    def predict(self, X_test, batch_size=128):
        batch_pred_list = []
        for X_test_batch in self.gen_batch(X_test, batch_size):
            batch_pred = self.sess.run(self.logits, {self.X:X_test_batch, self.keep_prob:1.0})
            batch_pred_list.append(batch_pred)
        return np.argmax(np.vstack(batch_pred_list), 1)
    # end method predict


    def gen_batch(self, arr, batch_size):
        for i in range(0, len(arr), batch_size):
            yield arr[i : i+batch_size]
    # end method gen_batch


    def decrease_lr(self, en_exp_decay, global_step, n_epoch, len_X, batch_size):
        if en_exp_decay:
            max_lr = 0.005
            min_lr = 0.001
            decay_rate = math.log(min_lr/max_lr) / (-n_epoch*len_X/batch_size)
            lr = max_lr*math.exp(-decay_rate*global_step)
        else:
            lr = 0.005
        return lr
    # end method adjust_lr


    def list_avg(self, l):
        return sum(l) / len(l)
    # end method list_avg
# end class
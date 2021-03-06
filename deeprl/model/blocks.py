import math
import tensorflow as tf


from deeprl.utils import import_class
from .utils import base_name, copy_variables


def parse_block(settings):
    class_name = settings["class"]
    if '.' not in class_name:
        class_name = 'deeprl.model.blocks.%s' % (class_name,)
    block_class = import_class(class_name)
    return block_class.parse(settings)

def parse_optimizer(settings):
    class_name = settings["class"]
    if '.' not in class_name:
        class_name = 'tensorflow.train.%s' % (class_name,)
    optimizer_class = import_class(class_name)
    return optimizer_class(**settings["kwargs"])

NONLINEARITIES = {
    'tanh': tf.tanh,
    'sigmoid': tf.sigmoid,
    'identity': lambda x: x,
    'softmax': tf.nn.softmax,
}

def ensure_list(sth):
    if isinstance(sth, (list, tuple)):
        return sth
    else:
        return [sth]

class Layer(object):
    def __init__(self, input_sizes, output_size, scope):
        """Cretes a neural network layer."""
        if type(input_sizes) != list:
            input_sizes = [input_sizes]

        self.input_sizes = input_sizes
        self.output_size = output_size
        self.scope       = scope or "Layer"

        with tf.variable_scope(self.scope):
            self.Ws = []
            for input_idx, input_size in enumerate(input_sizes):
                W_name = "W_%d" % (input_idx,)
                W_initializer =  tf.random_uniform_initializer(
                        -1.0 / math.sqrt(input_size), 1.0 / math.sqrt(input_size))
                W_var = tf.get_variable(W_name, (input_size, output_size), initializer=W_initializer)
                self.Ws.append(W_var)
            self.b = tf.get_variable("b", (output_size,), initializer=tf.constant_initializer(0))

    def __call__(self, xs):
        if type(xs) != list:
            xs = [xs]
        assert len(xs) == len(self.Ws), \
                "Expected %d input vectors, got %d" % (len(self.Ws), len(xs))
        with tf.variable_scope(self.scope):
            return sum([tf.matmul(x, W) for x, W in zip(xs, self.Ws)]) + self.b

    def variables(self):
        return [self.b] + self.Ws

    def copy(self, scope=None):
        scope = scope or self.scope + "_copy"

        with tf.variable_scope(scope) as sc:
            for v in self.variables():
                tf.get_variable(base_name(v), v.get_shape(),
                        initializer=lambda x,dtype=tf.float32: v.initialized_value())
            sc.reuse_variables()
            return Layer(self.input_sizes, self.output_size, scope=sc)


class MLP(object):
    @staticmethod
    def parse(settings):
        input_sizes    = settings['input_sizes']
        hiddens        = settings['hiddens']
        nonlinearities = [NONLINEARITIES[nl] for nl in settings['nonlinearities']]
        scope          = settings['scope']

        return MLP(input_sizes, hiddens, nonlinearities, scope=scope)

    def __init__(self, input_sizes, hiddens, nonlinearities, scope=None, given_layers=None):
        self.input_sizes = ensure_list(input_sizes)
        self.hiddens     = ensure_list(hiddens)
        nonlinearities = ensure_list(nonlinearities)
        self.input_nonlinearity, self.layer_nonlinearities = nonlinearities[0], nonlinearities[1:]
        self.scope = scope or "MLP"

        assert len(hiddens) == len(nonlinearities), \
                "Number of hiddens must be equal to number of nonlinearities"

        with tf.variable_scope(self.scope):
            if given_layers is not None:
                self.input_layer = given_layers[0]
                self.layers      = given_layers[1:]
            else:
                self.input_layer = Layer(input_sizes, hiddens[0], scope="input_layer")
                self.layers = []

                for l_idx, (h_from, h_to) in enumerate(zip(hiddens[:-1], hiddens[1:])):
                    self.layers.append(Layer(h_from, h_to, scope="hidden_layer_%d" % (l_idx,)))

    def batch_inputs(self, inputs_list):
        assert len(self.input_sizes) == 0, \
            "Multi-input batching not supported yet. Contribute?"

        batched = np.empty(len(inputs_list), self.input_sizes[0])
        for i, ipt in enumerate(inputs_list):
            batched[i] = 0 if ipt is None else ipt
        return batched


    def input_placeholder(self, name=None):
        if len(self.input_sizes) == 1:
            return tf.placeholder(tf.float32, (None, self.input_sizes[0]), name=name)
        else:
            return [tf.placeholder(tf.float32, (None, ins))
                    for ins in self.input_sizes]

    def output_shape(self):
        return (None, self.hiddens[-1],)

    def __call__(self, xs):
        if type(xs) != list:
            xs = [xs]
        with tf.variable_scope(self.scope):
            hidden = self.input_nonlinearity(self.input_layer(xs))
            for layer, nonlinearity in zip(self.layers, self.layer_nonlinearities):
                hidden = nonlinearity(layer(hidden))
            return hidden

    def variables(self):
        res = self.input_layer.variables()
        for layer in self.layers:
            res.extend(layer.variables())
        return res

    def copy(self, scope=None):
        scope = scope or self.scope + "_copy"
        nonlinearities = [self.input_nonlinearity] + self.layer_nonlinearities
        with tf.variable_scope(scope):
            given_layers = [self.input_layer.copy()] + [layer.copy() for layer in self.layers]
            return MLP(self.input_sizes, self.hiddens, nonlinearities, scope=scope,
                    given_layers=given_layers)

class SequenceWrapper(object):
    def __init__(self, seq, scope=None):
        self.seq   = seq
        self.scope = scope or "Seq"

    def __call__(self, x):
        with tf.variable_scope(self.scope):
            for el in self.seq:
                x = el(x)
            return x

    def variables(self):
        res = []
        for el in self.seq:
            if hasattr(el, 'variables'):
                res.extend(el.variables())
        return res

    def copy(self, scope=None):
        scope = scope or self.scope + "_copy"
        with tf.variable_scope(scope):
            new_seq = [el if type(el) is FunctionType else el.copy() for el in self.seq ]
            return SequenceWrapper(new_seq)

import theano
import theano.tensor as T

import numpy as np

from collections import OrderedDict
from functools import reduce
from theano.sandbox.rng_mrg import MRG_RandomStreams as RandomStreams

__all__ = [
  'softmin',
  'join',
  'joinc',
  'ldot',
  'log_barrier',
  'make_copy',
  'to_shared',
  'make_uniform',
  'make_normal',
  'get_srng',
  'grad_base'
]

join = lambda xs: reduce(lambda a, b: a + b, xs)
joinc = lambda xs, cs: join([ x * c for x, c in  zip(xs, cs)])
ldot = lambda xs, ys: join([ T.sum(x * y) for x, y in zip(xs, ys) ])

def get_srng(srng):
  if srng is None:
    # from theano.sandbox.cuda.rng_curand import CURAND_RandomStreams as RandomStreams
    return RandomStreams(seed=np.random.randint(2**30))
  else:
    return srng

def softmin(xs, alpha=1.0):
  alpha = np.float32(alpha)

  if hasattr(xs, '__len__'):
    exp_xs = [ T.exp(-x * alpha) for x in xs ]
    n = join(exp_xs)

    return [ ex / n for ex in exp_xs ]
  else:
    T.nnet.softmax(-xs * alpha)

def log_barrier(v, bounds):
  return -(T.log(v - bounds[0]) + T.log(bounds[1] - v))

def make_copy(shared):
  value = shared.get_value(borrow=True)
  return theano.shared(
    np.zeros(value.shape, dtype=value.dtype),
    broadcastable=shared.broadcastable
  )

def to_shared(var):
  return theano.shared(
    np.zeros(shape=(0, ) * var.ndim, dtype=var.dtype),
    broadcastable=var.broadcastable
  )

def make_uniform(shared, a, b, srng=None):
  srng = get_srng(srng)

  return srng.uniform(
    low=a, high=b,
    size=shared.get_value(borrow=True).shape,
    ndim=shared.ndim, dtype=shared.dtype
  )

def make_normal(shared, srng):
  srng = get_srng(srng)

  return srng.normal(
    size=shared.get_value(borrow=True).shape,
    ndim=shared.ndim, dtype=shared.dtype
  )

def grad_base(inputs, loss, params, outputs=(), epsilon=1.0e-6, momentum=None, norm_gradients = False):
  inputs_cached = [to_shared(i) for i in inputs]

  input_setter = OrderedDict()
  for inpc, inp in zip(inputs_cached, inputs):
    input_setter[inpc] = inp

  cache_inputs = theano.function(inputs, [], updates=input_setter, no_default_updates=True)

  inputs_givens = [
    (inp, inpc)
    for inp, inpc in zip(inputs, inputs_cached)
  ]

  grads = theano.grad(loss, params)

  if norm_gradients:
    grad_norm = T.sqrt(join([T.sum(g ** 2) for g in grads]) + epsilon)
    grads_ = [g / grad_norm for g in grads]
  else:
    grads_ = grads

  grads_cached = [make_copy(param) for param in params]

  grads_setter = OrderedDict()
  if momentum is None or momentum is False or momentum <= 0.0:
    for ngs, ng in zip(grads_cached, grads_):
      grads_setter[ngs] = ng
  else:
    one = T.constant(1, dtype='float32')

    for ngs, ng in zip(grads_cached, grads_):
      grads_setter[ngs] = ngs * momentum + (one - momentum) * ng

  cache_grads = theano.function(
    [], [], updates=grads_setter,
    no_default_updates=True,
    givens=inputs_givens
  )

  alpha = T.fscalar('alpha')

  probe_givens = [
    (param, param - alpha * ngrad)
    for param, ngrad in zip(params, grads_cached)
  ]

  get_loss = theano.function(
    [alpha], [loss] + list(outputs),
    givens=probe_givens + inputs_givens,
    no_default_updates=True,
    allow_input_downcast=True
  )

  params_setter = OrderedDict(probe_givens)

  set_params = theano.function(
    [alpha], [],
    updates=params_setter
  )

  return cache_inputs, cache_grads, get_loss, set_params
import functools
import unittest

import numpy as np
import pytest
import tensorflow as tf
from mock import Mock

from tfsnippet.dataflow import DataFlow
from tfsnippet.scaffold import TrainLoop
from tfsnippet.trainer import *


class BaseTrainerTestCase(tf.test.TestCase):

    def test_props(self):
        loop = Mock(valid_metric_name='valid_loss')
        t = BaseTrainer(loop)
        self.assertIs(loop, t.loop)
        self.assertEquals(
            (t.before_epochs, t.before_steps, t.after_steps, t.after_epochs),
            t.hook_lists
        )
        for hkl in t.hook_lists:
            self.assertIsInstance(hkl, HookList)

    def test_add_and_remove_hooks(self):
        loop = Mock(
            valid_metric_name='valid_loss',
            print_logs=Mock(return_value=None, __repr__=lambda o: 'print_logs')
        )
        df = Mock()
        val1 = Validator(loop, 1., [], df)
        val2 = Validator(loop, 2., [], df)
        anneal1 = AnnealingDynamicValue(1., .5)
        anneal2 = AnnealingDynamicValue(2., .5)

        # test add
        t = BaseTrainer(loop)
        t.log_after_epochs(3)
        t.log_after_steps(4)
        t.validate_after_steps(
            Mock(return_value=None, __repr__=lambda o: 'val_step'), 5)
        t.validate_after_epochs(
            Mock(return_value=None, __repr__=lambda o: 'val_epoch'), 6)
        t.anneal_after_steps(
            Mock(return_value=None, __repr__=lambda o: 'anneal_step'), 7)
        t.anneal_after_epochs(
            Mock(return_value=None, __repr__=lambda o: 'anneal_epoch'), 8)
        t.validate_after_steps(val1, 9)
        t.validate_after_epochs(val2, 10)
        t.anneal_after_steps(anneal1, 11)
        t.anneal_after_epochs(anneal2, 12)

        self.assertEquals('HookList()', repr(t.before_steps))
        self.assertEquals('HookList()', repr(t.before_epochs))
        steps_ans = 'HookList(val_step:5,{!r}:9,anneal_step:7,' \
                    '{!r}:11,print_logs:4)'.format(val1.run, anneal1.anneal)
        self.assertEquals(steps_ans, repr(t.after_steps))
        epochs_ans = 'HookList(val_epoch:6,{!r}:10,anneal_epoch:8,' \
                     '{!r}:12,print_logs:3)'.format(val2.run, anneal2.anneal)
        self.assertEquals(epochs_ans, repr(t.after_epochs))

        # test remove
        t.remove_log_hooks()
        steps_ans = 'HookList(val_step:5,{!r}:9,anneal_step:7,' \
                    '{!r}:11)'.format(val1.run, anneal1.anneal)
        self.assertEquals(steps_ans, repr(t.after_steps))
        epochs_ans = 'HookList(val_epoch:6,{!r}:10,anneal_epoch:8,' \
                     '{!r}:12)'.format(val2.run, anneal2.anneal)
        self.assertEquals(epochs_ans, repr(t.after_epochs))

        t.remove_validation_hooks()
        steps_ans = 'HookList(anneal_step:7,{!r}:11)'.format(anneal1.anneal)
        self.assertEquals(steps_ans, repr(t.after_steps))
        epochs_ans = 'HookList(anneal_epoch:8,{!r}:12)'.format(anneal2.anneal)
        self.assertEquals(epochs_ans, repr(t.after_epochs))

        t.remove_annealing_hooks()
        self.assertEquals('HookList()', repr(t.after_steps))
        self.assertEquals('HookList()', repr(t.after_epochs))

    def test_run(self):
        with self.test_session() as session:
            df = DataFlow.arrays([np.arange(6, dtype=np.float32)], batch_size=4)

            def log_message(m):
                logged_messages.append(m)
            logged_messages = []

            # test default loss weight and merged feed dict
            with TrainLoop([], max_epoch=2) as loop:
                t = BaseTrainer(loop)
                t._run_step = Mock(return_value=None)
                t._iter_steps = Mock(wraps=lambda: loop.iter_steps(df))
                t.before_epochs.add_hook(
                    functools.partial(log_message, 'before_epoch'))
                t.before_steps.add_hook(
                    functools.partial(log_message, 'before_step'))
                t.after_steps.add_hook(
                    functools.partial(log_message, 'after_step'))
                t.after_epochs.add_hook(
                    functools.partial(log_message, 'after_epoch'))

                t.run()
                self.assertEquals(4, len(t._run_step.call_args_list))
                for i, call_args in enumerate(t._run_step.call_args_list[:-2]):
                    call_session, call_payload = call_args[0]
                    self.assertIs(session, call_session)
                    self.assertEquals(i + 1, call_payload[0])
                    self.assertIsInstance(call_payload[1], tuple)
                    self.assertEquals(1, len(call_payload[1]))
                    np.testing.assert_equal(
                        np.arange(6, dtype=np.float32)[i * 4: (i + 1) * 4],
                        call_payload[1][0]
                    )

                self.assertEquals(
                    ['before_epoch', 'before_step', 'after_step',
                     'before_step', 'after_step', 'after_epoch'] * 2,
                    logged_messages
                )

            # test re-entrant error
            with TrainLoop([], max_epoch=1) as loop:
                t = BaseTrainer(loop)
                t._run_step = Mock(return_value=None)
                t._iter_steps = Mock(wraps=lambda: loop.iter_steps(df))

                def reentrant_error():
                    with pytest.raises(
                            RuntimeError, match=r'`run\(\)` is not re-entrant'):
                        t.run()
                reentrant_error = Mock(wraps=reentrant_error)
                t.after_steps.add_hook(reentrant_error)
                t.run()
                self.assertTrue(reentrant_error.called)


if __name__ == '__main__':
    unittest.main()

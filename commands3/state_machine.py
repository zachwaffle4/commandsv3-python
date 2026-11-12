# Copyright (c) FIRST and other WPILib contributors.
# Open Source Software; you can modify and/or share it under the terms of
# the WPILib BSD license file in the root directory of this project.

"""A declarative state machine that builds into a command."""

from __future__ import annotations

from collections.abc import Callable

from . import execution_context as _ec
from .command import DEFAULT_PRIORITY, Command
from .coroutine import fork, yield_
from .trigger import Trigger

__all__ = [
    "StateMachine",
    "TransitionNeedsConditionStage",
    "TransitionNeedsTargetStage",
]

#: A transition condition: a function returning whether it holds, or a
#: ``Trigger`` (which contributes its value as of the last event loop poll).
_Condition = Callable[[], bool] | Trigger


def _as_function(condition: _Condition) -> Callable[[], bool]:
    if isinstance(condition, Trigger):
        return condition.get_as_boolean
    return condition


class StateMachine:
    """
    A declarative state machine that can be used to implement complex command
    routines. Setup is done in stages: first a state machine is created and
    named, then states are added with ``add_state()``, then transitions
    between them are declared with ``State.switch_to()``, and finally
    ``build()`` turns it into a ``Command``::

        # Declare the state machine
        machine = StateMachine("Example State Machine")

        # Declare states
        state1 = machine.add_state(...)
        state2 = machine.add_state(...)
        state3 = machine.add_state(...)

        # Set the initial state
        machine.set_initial_state(state1)

        # Declare transitions
        state1.switch_to(state2).when(...)
        state2.switch_to(state3).when(...)

        scheduler.schedule(machine.build())

    Every state runs a single command. While a state's command is running, the
    state machine continually checks all the transitions that can be
    triggered from that state. If one is triggered, the machine cancels the
    state's command and moves to the next state as defined by that
    transition. If no transition is triggered by the time the command
    completes, the machine exits unless a ``when_complete()`` transition was
    specified from that state::

        # switch from state1 to state2 when foo is true
        state1.switch_to(state2).when(lambda: foo)

        # but if foo never becomes true, switch to state3 when state1 finishes
        state1.switch_to(state3).when_complete()

        # no transitions are defined from state2 or state3, so the state
        # machine exits when either state completes

    The state machine itself is a mutable builder rather than a command:
    ``build()`` returns the command, once, after which the machine can't be
    changed. Calling ``build()`` again returns the same command.

    If the command for a state can't be started (for instance because it
    shares a mechanism with a higher-priority command), the state machine
    command and the composition it belongs to are canceled.
    """

    def __init__(self, name: str) -> None:
        """
        :param name: The name of the state machine. It becomes the name of the
            command that ``build()`` returns, and appears in telemetry.
        """
        self._name = name
        self._priority = DEFAULT_PRIORITY
        self._initial_state: StateMachine.State | None = None
        self._states: list[StateMachine.State] = []
        # Marks the state machine as no longer accepting new states. Used when
        # a no-argument switch_from_any() is called, to prevent surprising
        # behavior if users try to define new states afterward.
        self._closed_for_new_states = False
        self._command: Command | None = None

    def set_priority(self, priority: int) -> None:
        """
        Sets the priority of the state machine command.

        Because a state machine doesn't require any mechanisms itself, its
        priority is inherited by any state command whose own priority is lower.
        That makes the commands in the state machine harder to interrupt than
        they would be on their own, which is useful for keeping them from being
        interrupted by commands that otherwise could.
        """
        self._throw_if_built()
        self._priority = priority

    def add_state(self, command: Command) -> StateMachine.State:
        """
        Adds a new state to the state machine. State transitions can be
        specified on it with ``State.switch_to()``.

        :param command: The command for the state to run.
        :raises RuntimeError: if ``switch_from_any()`` has already been called
            with no arguments, or the state machine has been built.
        """
        self._throw_if_built()
        if self._closed_for_new_states:
            raise RuntimeError(
                "Cannot add new states to a state machine after switch_from_any() "
                "has been called with no arguments"
            )
        state = StateMachine.State(self, command)
        self._states.append(state)
        return state

    def switch_from_any(
        self, *states: StateMachine.State
    ) -> TransitionNeedsTargetStage:
        """
        Sets up a transition from any of the given states to a specific state.
        If no states are given, the transition applies to every state in the
        state machine *at the time this method is called*, and the state
        machine no longer permits states to be added::

            machine.switch_from_any(state1, state2, state3).to(state4).when(foo)

            # Functionally equivalent to:
            state1.switch_to(state4).when(foo)
            state2.switch_to(state4).when(foo)
            state3.switch_to(state4).when(foo)

            # Set up an early exit condition from any state. Using this
            # no-argument form prevents states from being added later!
            machine.switch_from_any().to_exit_state_machine().when(bar)

            # Functionally equivalent to:
            state1.exit_state_machine().when(bar)
            state2.exit_state_machine().when(bar)
            state3.exit_state_machine().when(bar)
            state4.exit_state_machine().when(bar)

        :returns: A builder for the transition.
        """
        self._throw_if_built()
        if not states:
            self._closed_for_new_states = True
            return TransitionNeedsTargetStage(list(self._states))
        return TransitionNeedsTargetStage(list(states))

    def set_initial_state(self, initial_state: StateMachine.State) -> None:
        """
        Sets the initial state for the state machine. This must be called
        before ``build()``. Calling it again replaces the previous one.

        :raises ValueError: if the state belongs to a different state machine.
        """
        self._throw_if_built()
        if initial_state._state_machine is not self:
            raise ValueError("Cannot set initial state in a different state machine")
        self._initial_state = initial_state

    def build(self) -> Command:
        """
        Creates the command that runs this state machine. It has no
        requirements of its own (the commands for its states may), the name
        the state machine was created with, and the priority from
        ``set_priority()``.

        After this the state machine can no longer be modified. Calling it
        again returns the same command.

        :raises RuntimeError: if no initial state was set.
        """
        if self._command is None:
            if self._initial_state is None:
                raise RuntimeError(
                    f"{self._name} does not have an initial state. "
                    "Use .set_initial_state() to provide one."
                )
            self._command = (
                Command.no_requirements(self._run)
                .with_priority(self._priority)
                .named(self._name)
            )
        return self._command

    def _throw_if_built(self) -> None:
        if self._command is not None:
            raise RuntimeError(
                f"The state machine {self._name!r} can't be modified after build()"
            )

    async def _run(self) -> None:
        scheduler = _ec.require_current_scheduler()
        current = self._initial_state

        while current is not None:
            command = current._command
            # The state machine exits if the command can't be forked, which
            # happens if it shares requirements with a higher-priority
            # command: fork() raises and takes the composition down.
            fork(command)
            current._run_enter_callbacks()
            did_yield = False
            moved_on = False

            while scheduler.is_running(command):
                for transition in current._transitions:
                    if transition.should_transition():
                        # Cancel the state's command and move to the next
                        # state, skipping the yield below so the next state's
                        # command starts in the same tick. A next state of
                        # None exits the state machine immediately. To keep a
                        # state that transitions to itself from looping
                        # forever, a transition only fires on a rising edge of
                        # its condition.
                        current._run_exit_callbacks()
                        scheduler.cancel(command)
                        current = self._verify_state(transition.next_state())
                        moved_on = True
                        break
                if moved_on:
                    break

                # Yield after checking all the transitions. Skipped if one
                # fired.
                await yield_()
                did_yield = True

            if moved_on:
                continue

            # No transition was hit before the command completed, so move to
            # the next configured state. A one-shot command completes inside
            # the fork() call above and never enters the loop, so it would
            # never yield; make sure the state machine yields at least once
            # per state. (This differs slightly from a sequence, which runs
            # commands as fast as it can.)
            current._run_exit_callbacks()
            current = self._verify_state(current._next_state())
            if not did_yield and current is not None:
                # No need to yield if the state machine is exiting.
                await yield_()

    def _verify_state(self, next_state: StateMachine.State | None):
        if next_state is None or next_state._state_machine is self:
            return next_state

        # Bad user setup
        raise RuntimeError(
            "The next state does not belong to this state machine. "
            f"Check the state for {next_state._command.name}"
        )

    class State:
        """
        A state in a state machine. Each state has a command that runs while
        it is active. A state can transition to other states when some
        condition is met while it's active, or automatically transition to
        another state when it completes if no transition condition was met. A
        state with no transitions never transitions to another state, and
        makes the state machine exit when it completes; likewise a state with
        no incoming transitions is never active.

        Created with ``StateMachine.add_state()``.
        """

        def __init__(self, state_machine: StateMachine, command: Command) -> None:
            self._state_machine = state_machine
            self._command = command
            # The possible states to transition to when this one completes.
            self._completions: list[_Completion] = []
            # The state to transition to by default when this one completes.
            # May return None, which exits the state machine.
            self._default_next_state: Callable[[], StateMachine.State | None] = (
                _exit_state_machine
            )
            # The transitions that can be triggered while this state is active.
            # If several are triggered at once, the first in the list is used.
            self._transitions: list[_Transition] = []
            self._enter_callbacks: list[Callable[[], None]] = []
            self._exit_callbacks: list[Callable[[], None]] = []

        def on_enter(self, callback: Callable[[], None]) -> None:
            """
            Adds a function to call when this state is entered. Callbacks are
            called immediately after the state's command is scheduled, in the
            order they were added.

            If a callback schedules any commands, they are scoped to the
            lifetime of the whole state machine, *not* this state's lifetime.
            """
            self._state_machine._throw_if_built()
            self._enter_callbacks.append(callback)

        def on_exit(self, callback: Callable[[], None]) -> None:
            """
            Adds a function to call when this state is exited. Callbacks are
            called immediately before the state's command is canceled, in the
            order they were added. If the command finishes naturally, they
            are called right after it completes and before the next state is
            entered.

            They are not called if the whole state machine is canceled while
            the state is active.
            """
            self._state_machine._throw_if_built()
            self._exit_callbacks.append(callback)

        def switch_to(
            self, to: StateMachine.State | Callable[[], StateMachine.State | None]
        ) -> TransitionNeedsConditionStage:
            """
            Starts building a transition to the given state.

            :param to: The state to transition to, or a function that picks it
                at the time the transition's condition is met. A function that
                returns ``None`` makes the transition exit the state machine.
            :raises ValueError: if a state belongs to a different state machine.
            """
            return TransitionNeedsTargetStage([self]).to(to)

        def exit_state_machine(self) -> TransitionNeedsConditionStage:
            """
            Starts building a transition that exits the state machine when it
            is triggered, rather than moving to a different state.
            """
            return TransitionNeedsTargetStage([self]).to_exit_state_machine()

        def _run_enter_callbacks(self) -> None:
            for callback in self._enter_callbacks:
                callback()

        def _run_exit_callbacks(self) -> None:
            for callback in self._exit_callbacks:
                callback()

        def _next_state(self) -> StateMachine.State | None:
            for completion in self._completions:
                if completion.should_transition():
                    return completion.next_state()

            # No conditional transition was met, so use the default next state.
            # If that was never set, or was set to exit, the state machine
            # exits.
            return self._default_next_state()

        def _add_transition(self, transition: _Transition) -> None:
            self._state_machine._throw_if_built()
            self._transitions.append(transition)

        def _set_next_state(
            self, next_state: Callable[[], StateMachine.State | None]
        ) -> None:
            self._state_machine._throw_if_built()
            self._default_next_state = next_state

        def _add_completion(self, completion: _Completion) -> None:
            self._state_machine._throw_if_built()
            # Replace any existing completion made with the same condition
            # object. Compared by identity on purpose: a condition may be an
            # object whose == compares values, and what matters here is
            # whether it's the very condition passed in before.
            self._completions = [
                existing
                for existing in self._completions
                if existing.condition is not completion.condition
            ]
            self._completions.append(completion)


def _exit_state_machine() -> StateMachine.State | None:
    return None


class TransitionNeedsTargetStage:
    """
    A builder for a transition from one or more states to another. Use
    ``to()`` to specify the target state, or ``to_exit_state_machine()``.
    """

    def __init__(self, from_states: list[StateMachine.State]) -> None:
        self._from = from_states

    def to(
        self, to: StateMachine.State | Callable[[], StateMachine.State | None]
    ) -> TransitionNeedsConditionStage:
        """
        Specifies the target state to transition to.

        :param to: The state to transition to, or a function that picks it at
            the time the transition's condition is met. A function that returns
            ``None`` makes the transition exit the state machine. A state
            returned by a function that belongs to a different state machine
            raises when the transition fires.
        :raises ValueError: if a state belongs to a different state machine.
        :returns: A builder to specify the transition condition.
        """
        if isinstance(to, StateMachine.State):
            for state in self._from:
                if state._state_machine is not to._state_machine:
                    raise ValueError(
                        "Cannot transition to a state in a different state machine"
                    )
            target = to
            return TransitionNeedsConditionStage(self._from, lambda: target)
        return TransitionNeedsConditionStage(self._from, to)

    def to_exit_state_machine(self) -> TransitionNeedsConditionStage:
        """
        Specifies that the transition exits the state machine when it is
        triggered, rather than moving to a different state.

        :returns: A builder to specify the transition condition.
        """
        return TransitionNeedsConditionStage(self._from, _exit_state_machine)


class TransitionNeedsConditionStage:
    """
    A builder to set the conditions for a transition from one state to
    another. Use ``when()`` to make the transition occur when some external
    condition becomes true, or ``when_complete()`` to make it occur when the
    originating state completes without having reached any other transition
    first.
    """

    def __init__(
        self,
        from_states: list[StateMachine.State],
        target: Callable[[], StateMachine.State | None],
    ) -> None:
        self._originating_states = from_states
        # A target of None exits the state machine.
        self._target = target

    def when(self, condition: _Condition) -> None:
        """
        Adds a transition that is triggered when ``condition`` becomes true.

        **This has no effect if the originating state is a one-shot command
        that never yields.** Use ``when_complete()`` for transitions from
        one-shot commands.

        If several transitions are triggered in the same scheduler tick, the
        first one fires and the rest are ignored::

            state1.switch_to(state2).when(lambda: foo)

            # never fires, because the first transition is checked first
            state1.switch_to(state3).when(lambda: foo)

        :param condition: A function, or a ``Trigger``, that triggers the
            transition.
        """
        # One transition object is shared by every originating state. It
        # tracks the condition's previous value to detect a rising edge, so
        # that value is shared too.
        transition = _Transition(self._target, _as_function(condition))
        for state in self._originating_states:
            state._add_transition(transition)

    def when_complete(self) -> None:
        """
        Adds a transition to the target state for when the originating state
        completes without having triggered any other transition first. If
        this is called more than once for the same originating state, the
        later call replaces the earlier one. A ``when_complete_and()``
        transition takes precedence over a ``when_complete()`` one if its
        condition is met when the state exits::

            state1.switch_to(state2).when_complete()
            state1.switch_to(state3).when_complete()  # replaces the previous one
            state1.exit_state_machine().when_complete_and(...)  # wins if met
        """
        for state in self._originating_states:
            state._set_next_state(self._target)

    def when_complete_and(self, condition: _Condition) -> None:
        """
        Like ``when()``, but only triggers when the originating state
        completes *and* ``condition`` is also met. ``when_complete_and()``
        transitions are checked in the order they were declared and take
        precedence over any ``when_complete()`` transition. Adding one with
        the same condition object as an earlier one replaces it.

        :param condition: A function, or a ``Trigger``, that must hold when the
            state completes.
        """
        completion = _Completion(self._target, condition)
        for state in self._originating_states:
            state._add_completion(completion)


class _Completion:
    """
    Like ``_Transition``, but doesn't track the condition's history. It is
    only checked once, when the originating state completes.
    """

    def __init__(
        self,
        next_supplier: Callable[[], StateMachine.State | None],
        condition: _Condition,
    ) -> None:
        self._next_supplier = next_supplier
        #: The condition as the caller passed it, kept for comparing by identity.
        self.condition = condition
        self._function = _as_function(condition)

    def should_transition(self) -> bool:
        return self._function()

    def next_state(self) -> StateMachine.State | None:
        return self._next_supplier()


class _Transition:
    """
    Like ``_Completion``, but tracks the condition's previous value to avoid
    infinite loops. It is checked every tick while the originating state is
    active.
    """

    def __init__(
        self,
        next_supplier: Callable[[], StateMachine.State | None],
        condition: Callable[[], bool],
    ) -> None:
        self._next_supplier = next_supplier
        self._condition = condition
        self._previous_signal = False

    def should_transition(self) -> bool:
        # Wrap the condition in a rising edge detector so it only triggers once
        # per rise. This prevents trouble when a state transitions to itself:
        #   state1.switch_to(state1).when(lambda: foo)
        # If the condition is itself a rising edge detector, this is redundant
        # but harmless.
        current_value = self._condition()
        is_rising_edge = current_value and not self._previous_signal
        self._previous_signal = current_value
        return is_rising_edge

    def next_state(self) -> StateMachine.State | None:
        return self._next_supplier()

# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Detent Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Session manager for coordinating checkpoint, pipeline, and IPC."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from detent.checkpoint.engine import CheckpointEngine
    from detent.ipc.channel import IPCControlChannel
    from detent.pipeline.pipeline import VerificationPipeline
    from detent.schema import AgentAction

from detent.feedback.synthesizer import FeedbackSynthesizer
from detent.observability.metrics import record_rollback, record_tool_call
from detent.observability.tracer import get_tracer
from detent.pipeline.result import VerificationResult
from detent.proxy.types import DetentSessionConflictError, IPCMessage, IPCMessageType

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages verification session lifecycle.

    Coordinates:
    - Session state (start, active, end)
    - SAVEPOINT creation before tool calls
    - Pipeline execution
    - Feedback synthesis
    - IPC message dispatch
    """

    def __init__(
        self,
        checkpoint_engine: CheckpointEngine,
        pipeline: VerificationPipeline,
        ipc_channel: IPCControlChannel,
        synthesizer: FeedbackSynthesizer | None = None,
    ) -> None:
        """Initialize session manager.

        Args:
            checkpoint_engine: Checkpoint engine for SAVEPOINTs
            pipeline: Verification pipeline
            ipc_channel: IPC control channel
            synthesizer: Feedback synthesizer (optional)
        """
        self.checkpoint_engine = checkpoint_engine
        self.pipeline = pipeline
        self.ipc_channel = ipc_channel
        self.synthesizer = synthesizer or FeedbackSynthesizer()

        self.is_active = False
        self.session_id: str | None = None
        self._checkpoint_refs: list[str] = []
        self._lock = asyncio.Lock()

    async def start_session(self, session_id: str) -> None:
        """Start a verification session.

        Args:
            session_id: Unique session identifier

        Raises:
            DetentSessionConflictError if session already active
        """
        async with self._lock:
            if self.is_active:
                raise DetentSessionConflictError(f"Session already active: {self.session_id}")

            self.is_active = True
            self.session_id = session_id
            self._checkpoint_refs = []

        logger.info("[session] started session %s", session_id)

        # Notify IPC
        await self.ipc_channel.send_message(
            IPCMessage(
                type=IPCMessageType.SESSION_START,
                data={"session_id": session_id},
                timestamp=datetime.now(UTC).isoformat(),
            )
        )

    async def end_session(self) -> None:
        """End the current verification session."""
        if not self.is_active:
            return

        session_id = self.session_id

        async with self._lock:
            self.is_active = False
            self.session_id = None
            self._checkpoint_refs = []

        logger.info("[session] ended session %s", session_id)

        # Notify IPC
        await self.ipc_channel.send_message(
            IPCMessage(
                type=IPCMessageType.SESSION_END,
                data={"session_id": session_id},
                timestamp=datetime.now(UTC).isoformat(),
            )
        )

    async def intercept_tool_call(self, action: AgentAction | None) -> VerificationResult:
        """Intercept and verify a tool call.

        Args:
            action: Normalized agent action

        Returns:
            Verification result (pass/fail with findings)
        """
        if action is None:
            logger.debug("[session] no action to verify; skipping pipeline")
            return VerificationResult(
                stage="session",
                passed=True,
                findings=[],
                duration_ms=0.0,
            )
        if not self.is_active:
            logger.warning("[session] tool call intercepted but no active session")
            return VerificationResult(
                stage="session",
                passed=False,
                findings=[],
                duration_ms=0.0,
            )

        # Create checkpoint reference
        checkpoint_ref = f"chk_before_write_{len(self._checkpoint_refs):03d}"
        tracer = get_tracer(__name__)
        span_attrs = {
            "detent.session_id": self.session_id,
            "detent.tool_call_id": action.tool_call_id,
            "detent.action_type": action.action_type,
            "detent.agent": action.agent,
            "detent.risk_level": action.risk_level.value,
            "detent.file_path": action.file_path or "<unknown>",
        }

        try:
            with tracer.start_as_current_span("detent.tool_call", attributes=span_attrs) as span:
                # Create SAVEPOINT before running pipeline
                files = [action.file_path] if action.file_path else []
                await self.checkpoint_engine.savepoint(checkpoint_ref, files)

                async with self._lock:
                    self._checkpoint_refs.append(checkpoint_ref)

                logger.info("[session] created checkpoint %s", checkpoint_ref)

                # Update action with checkpoint ref
                action.checkpoint_ref = checkpoint_ref
                span.set_attribute("detent.checkpoint_ref", checkpoint_ref)

                # Notify IPC of intercepted tool
                await self.ipc_channel.send_message(
                    IPCMessage(
                        type=IPCMessageType.TOOL_INTERCEPTED,
                        data={
                            "tool_call_id": action.tool_call_id,
                            "action": action.model_dump(),
                        },
                        timestamp=datetime.now(UTC).isoformat(),
                    )
                )

                # Run verification pipeline
                result = await self.pipeline.run(action)

                span.set_attribute("detent.tool_call.passed", result.passed)
                record_tool_call(action.agent, action.action_type.value, result.passed)

                if result.passed:
                    await self._on_verification_pass(action, result)
                else:
                    await self._on_verification_fail(action, result, checkpoint_ref)

                return result
        except Exception as e:
            logger.error("[session] tool interception failed: %s", e)
            return VerificationResult(
                stage="session",
                passed=False,
                findings=[],
                duration_ms=0.0,
            )

    async def _on_verification_pass(
        self,
        action: AgentAction,
        result: VerificationResult,
    ) -> None:
        """Handle verification pass."""
        logger.info(
            "[session] verification passed for tool %s",
            action.tool_name,
        )

        # Notify IPC
        await self.ipc_channel.send_message(
            IPCMessage(
                type=IPCMessageType.VERIFICATION_RESULT,
                data={
                    "tool_call_id": action.tool_call_id,
                    "status": "allowed",
                    "checkpoint_ref": action.checkpoint_ref,
                },
                timestamp=datetime.now(UTC).isoformat(),
            )
        )

    async def _on_verification_fail(
        self,
        action: AgentAction,
        result: VerificationResult,
        checkpoint_ref: str,
    ) -> None:
        """Handle verification failure."""
        record_rollback(result.stage)
        logger.info(
            "[session] verification failed for tool %s, rolling back",
            action.tool_name,
        )

        # Synthesize feedback
        feedback = self.synthesizer.synthesize(result, action)

        # Rollback checkpoint
        await self.checkpoint_engine.rollback(checkpoint_ref)

        # Notify IPC of rollback
        await self.ipc_channel.send_message(
            IPCMessage(
                type=IPCMessageType.ROLLBACK_INSTRUCTION,
                data={
                    "tool_call_id": action.tool_call_id,
                    "checkpoint_ref": checkpoint_ref,
                    "feedback": feedback.model_dump(),
                },
                timestamp=datetime.now(UTC).isoformat(),
            )
        )

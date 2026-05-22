import { computed, nextTick, ref, type ComputedRef, type Ref, type ShallowRef } from "vue";

import type { BuddyMascotMotionDebugConfig } from "../stores/buddyMascotDebug.ts";
import type { BuddyMascotDebugAction } from "./buddyMascotDebug.ts";
import {
  BUDDY_IDLE_ANIMATION_MAX_DELAY_MS,
  BUDDY_IDLE_ANIMATION_MIN_DELAY_MS,
  BUDDY_IDLE_TAIL_SWITCH_DURATION_MS,
  BUDDY_IDLE_VIRTUAL_CURSOR_CHASE_LOOP_PERIOD_MS,
  BUDDY_IDLE_VIRTUAL_CURSOR_ORBIT_LAP_DURATION_MS,
  chooseBuddyIdleAnimationAction,
  isBuddyRoamTargetReached,
  isBuddyVirtualCursorFollowTargetReached,
  randomBetween,
  resolveBuddyRoamFacing,
  resolveBuddyRoamStepPosition,
  resolveBuddyRoamTargetPosition,
  resolveBuddyVirtualCursorFollowTargetPosition as resolveBuddyVirtualCursorFollowTargetPositionFromModel,
  resolveMascotMoveDurationMs,
  resolveRandomVirtualCursorChasePosition as resolveRandomVirtualCursorChasePositionFromModel,
  resolveVirtualCursorChaseLoopPosition,
  resolveVirtualCursorChaseLoopTangentAngle,
  resolveVirtualCursorOrbitAngle,
  resolveVirtualCursorOrbitPosition,
  resolveVirtualCursorOrbitTangentAngle,
  type BuddyMascotFacing,
} from "./buddyMascotMotionModel.ts";
import {
  DEFAULT_BUDDY_MARGIN,
  DEFAULT_BUDDY_SIZE,
  clampBuddyPosition,
  type BuddyPosition,
  type BuddyViewport,
} from "./buddyPosition.ts";
import { dispatchVirtualInputEvents } from "./buddyVirtualPointerEvents.ts";
import {
  BUDDY_VIRTUAL_CURSOR_MAX_FLIGHT_DURATION_MS,
  BUDDY_VIRTUAL_CURSOR_MAX_ROTATE_TRANSITION_MS,
  BUDDY_VIRTUAL_CURSOR_RESTING_ANGLE_DEG,
  BUDDY_VIRTUAL_CURSOR_SIZE,
  interpolateBuddyPosition,
  resolveBoxCenter,
  resolveContinuousVirtualCursorAngle,
  resolveDefaultVirtualCursorPosition,
  resolveElementCenterPoint,
  resolveSmoothedVirtualCursorAngle,
  resolveVirtualCursorFlightAngle,
  resolveVirtualCursorLaunchPosition,
  resolveVirtualCursorMoveDurationMs,
  resolveVirtualCursorPositionForClientPoint,
  resolveVirtualCursorRotateDurationMs,
} from "./buddyVirtualCursorGeometry.ts";
import { shouldHandleVirtualCursorPointerDown } from "./buddyVirtualOperationInteractionPolicy.ts";
import type { BuddyVirtualOperationToken } from "./useBuddyVirtualOperationLifecycle.ts";

export type BuddyMood = "idle" | "thinking" | "speaking" | "error";
export type BuddyMascotMotion = "idle" | "roam" | "hop";
export type VirtualCursorPhase = "hidden" | "launching" | "active" | "returning";
type BuddyIdleRunOptions = { force?: boolean };
type VirtualCursorIdleActionMode = "none" | "orbit" | "chase";

type UseBuddyMascotMotionControllerOptions = {
  activeRunId: Ref<string | null>;
  activeVirtualOperationToken: ShallowRef<BuddyVirtualOperationToken | null>;
  clearSpeakingIdleTimer: () => void;
  isDragging: ComputedRef<boolean>;
  isPanelFullscreen: Ref<boolean>;
  isPanelOpen: Ref<boolean>;
  isVirtualOperationInterrupted: (token: BuddyVirtualOperationToken | null) => boolean;
  isVirtualOperationRunning: ComputedRef<boolean>;
  motionConfig: Ref<BuddyMascotMotionDebugConfig>;
  mood: Ref<BuddyMood>;
  persistPosition: () => void;
  position: Ref<BuddyPosition>;
  queuedTurns: Ref<unknown[]>;
  setVirtualCursorEnabled: (enabled: boolean) => void;
  tapNonce: Ref<number>;
  viewport: Ref<BuddyViewport>;
  virtualCursorEnabled: Ref<boolean>;
  waitForVirtualOperation: (timeoutMs: number, token?: BuddyVirtualOperationToken | null) => Promise<void>;
};

const BUDDY_VIRTUAL_CURSOR_STAR_ANGLE_DEG = 0;
const BUDDY_VIRTUAL_CURSOR_MORPH_DURATION_MS = 360;
const BUDDY_VIRTUAL_CURSOR_READY_FRAME_DELAY_MS = 80;
const BUDDY_VIRTUAL_CURSOR_MOVE_TRANSITION_MS = 180;
const BUDDY_VIRTUAL_CURSOR_ROTATE_TRANSITION_MS = 120;
const BUDDY_VIRTUAL_CURSOR_FLIGHT_SETTLE_MS = 80;
const BUDDY_VIRTUAL_CURSOR_DOCKED_SCALE = 0.72;
const BUDDY_VIRTUAL_CURSOR_ACTIVE_SCALE = 1;
const BUDDY_VIRTUAL_OPERATION_TYPE_CHARACTER_DELAY_MS = 18;
const VIRTUAL_CURSOR_STAR_PATH =
  "M0-72 C5-46 18-33 44-28 C18-23 5-10 0 16 C-5-10 -18-23 -44-28 C-18-33 -5-46 0-72Z";
const VIRTUAL_CURSOR_SHAPE_PATH =
  "M0-72 C14-35 33 5 52 34 C27 35 13 46 0 64 C-13 46 -27 35 -52 34 C-33 5 -14-35 0-72Z";

export function useBuddyMascotMotionController({
  activeRunId,
  activeVirtualOperationToken,
  clearSpeakingIdleTimer,
  isDragging,
  isPanelFullscreen,
  isPanelOpen,
  isVirtualOperationInterrupted,
  isVirtualOperationRunning,
  motionConfig,
  mood,
  persistPosition,
  position,
  queuedTurns,
  setVirtualCursorEnabled,
  tapNonce,
  viewport,
  virtualCursorEnabled,
  waitForVirtualOperation,
}: UseBuddyMascotMotionControllerOptions) {
  const virtualCursorPosition = ref(resolveDefaultVirtualCursorPosition(viewport.value, position.value));
  const virtualCursorPhase = ref<VirtualCursorPhase>("hidden");
  const virtualCursorPath = ref(VIRTUAL_CURSOR_STAR_PATH);
  const virtualCursorMorphAnimation = ref<{ key: number; values: string; durationMs: number } | null>(null);
  const virtualCursorAngleDeg = ref(BUDDY_VIRTUAL_CURSOR_RESTING_ANGLE_DEG);
  const virtualCursorScale = ref(BUDDY_VIRTUAL_CURSOR_DOCKED_SCALE);
  const virtualCursorMoveDurationMs = ref(BUDDY_VIRTUAL_CURSOR_MOVE_TRANSITION_MS);
  const virtualCursorRotateDurationMs = ref(BUDDY_VIRTUAL_CURSOR_ROTATE_TRANSITION_MS);
  const virtualCursorDetached = ref(false);
  const virtualCursorDragging = ref(false);
  const virtualCursorIdleActionMode = ref<VirtualCursorIdleActionMode>("none");
  const avatarHopCycle = ref(0);
  const tailSwitchNonce = ref(0);
  const avatarElement = ref<HTMLElement | null>(null);
  const virtualCursorAnimateElement = ref<SVGAnimationElement | null>(null);
  const mascotLook = ref({ x: 0, y: 0 });
  const mascotMotion = ref<BuddyMascotMotion>("idle");
  const mascotFacing = ref<BuddyMascotFacing>("front");
  const mascotMoveDurationMs = ref(motionConfig.value.moveDurationMs);
  const debugDragging = ref(false);

  let virtualCursorDrag: {
    pointerId: number;
    startX: number;
    startY: number;
    startPosition: BuddyPosition;
  } | null = null;
  let mascotLookFrameId: number | null = null;
  let buddyRoamTimerId: number | null = null;
  let buddyRoamMotionTimerId: number | null = null;
  let buddyRoamStepTimerId: number | null = null;
  let buddyRoamTargetPosition: BuddyPosition | null = null;
  let buddyRoamSequenceId = 0;
  let buddyVirtualCursorFollowMotionTimerId: number | null = null;
  let buddyVirtualCursorFollowStepTimerId: number | null = null;
  let buddyVirtualCursorFollowTargetPosition: BuddyPosition | null = null;
  let buddyVirtualCursorFollowSequenceId = 0;
  let buddyVirtualCursorIdleFrameId: number | null = null;
  let virtualCursorTransitionTimerId: number | null = null;
  let virtualCursorTransitionFrameId: number | null = null;
  let virtualCursorFlightFrameId: number | null = null;
  let virtualCursorFlightTrackingFrameId: number | null = null;
  let virtualCursorFlightTracking: { fromPosition: BuddyPosition; toPosition: BuddyPosition; startedAtMs: number; durationMs: number } | null = null;
  let virtualCursorTrackingPosition: BuddyPosition | null = null;
  let virtualCursorAngleFrameTimestampMs: number | null = null;
  let virtualCursorMorphAnimationKey = 0;
  let virtualCursorPickupPending = false;
  let buddyDebugActionTimerId: number | null = null;
  let pendingMascotLookPointer: { x: number; y: number } | null = null;

  const isMascotDragging = computed(() => isDragging.value || debugDragging.value);
  const shouldBuddyFollowVirtualCursor = computed(() => virtualCursorEnabled.value && virtualCursorIdleActionMode.value !== "orbit");
  const canBuddyRoam = computed(() =>
    !isPanelOpen.value &&
    !virtualCursorEnabled.value &&
    virtualCursorIdleActionMode.value === "none" &&
    virtualCursorPhase.value === "hidden" &&
    mood.value === "idle" &&
    !isMascotDragging.value &&
    queuedTurns.value.length === 0 &&
    activeRunId.value === null,
  );
  const virtualCursorStyle = computed(() => ({
    "--buddy-widget-virtual-cursor-morph-duration-ms": `${BUDDY_VIRTUAL_CURSOR_MORPH_DURATION_MS}ms`,
    "--buddy-widget-virtual-cursor-move-duration-ms": `${virtualCursorMoveDurationMs.value}ms`,
    "--buddy-widget-virtual-cursor-rotate-duration-ms": `${virtualCursorRotateDurationMs.value}ms`,
    "--buddy-widget-virtual-cursor-angle": `${virtualCursorAngleDeg.value}deg`,
    "--buddy-widget-virtual-cursor-scale": virtualCursorScale.value,
    translate: `${virtualCursorPosition.value.x}px ${virtualCursorPosition.value.y}px`,
    rotate: "var(--buddy-widget-virtual-cursor-angle)",
  }));
  const isVirtualCursorRendered = computed(() => virtualCursorPhase.value !== "hidden");
  const shouldFloatVirtualCursor = computed(() =>
    virtualCursorPhase.value === "active" && !virtualCursorDragging.value && virtualCursorIdleActionMode.value === "none",
  );

  function activateVirtualCursor() {
    if (virtualCursorIdleActionMode.value === "none") {
      cancelBuddyRoamTimers();
      clearBuddyDebugActionTimer();
    }
    cancelMascotLookFrame();
    pendingMascotLookPointer = null;
    virtualCursorDragging.value = false;
    startVirtualCursorLaunch();
    updateMascotLookFromVirtualCursor();
  }

  function deactivateVirtualCursor() {
    virtualCursorPickupPending = false;
    clearVirtualCursorDrag();
    cancelBuddyVirtualCursorFollowTimers();
    startVirtualCursorReturn();
  }

  function handleVirtualCursorPointerDown(event: PointerEvent) {
    if (
      !shouldHandleVirtualCursorPointerDown({
        isOperationRunning: isVirtualOperationRunning.value,
        phase: virtualCursorPhase.value,
      })
    ) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    cancelBuddyRoamTimers();
    clearBuddyDebugActionTimer();
    clearVirtualCursorDrag();
    virtualCursorDetached.value = true;
    virtualCursorDragging.value = true;
    virtualCursorDrag = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      startPosition: { ...virtualCursorPosition.value },
    };
    window.addEventListener("pointermove", handleVirtualCursorPointerMove);
    window.addEventListener("pointerup", handleVirtualCursorPointerUp);
  }

  function handleVirtualCursorPointerMove(event: PointerEvent) {
    if (!virtualCursorDrag || virtualCursorDrag.pointerId !== event.pointerId) {
      return;
    }
    event.preventDefault();
    const deltaX = event.clientX - virtualCursorDrag.startX;
    const deltaY = event.clientY - virtualCursorDrag.startY;
    moveVirtualCursorTo(
      clampBuddyPosition(
        {
          x: virtualCursorDrag.startPosition.x + deltaX,
          y: virtualCursorDrag.startPosition.y + deltaY,
        },
        viewport.value,
        BUDDY_VIRTUAL_CURSOR_SIZE,
        DEFAULT_BUDDY_MARGIN,
      ),
      { durationMs: 0, rotateDurationMs: 0 },
    );
    updateMascotLookFromVirtualCursor();
    requestBuddyFollowVirtualCursor();
  }

  function handleVirtualCursorPointerUp(event: PointerEvent) {
    if (!virtualCursorDrag || virtualCursorDrag.pointerId !== event.pointerId) {
      return;
    }
    event.preventDefault();
    requestBuddyFollowVirtualCursor();
    settleVirtualCursorRotation();
    clearVirtualCursorDrag();
  }

  function clearVirtualCursorDrag() {
    virtualCursorDrag = null;
    virtualCursorDragging.value = false;
    window.removeEventListener("pointermove", handleVirtualCursorPointerMove);
    window.removeEventListener("pointerup", handleVirtualCursorPointerUp);
  }

  function handleMascotLookPointerMove(event: PointerEvent) {
    if (virtualCursorEnabled.value) {
      return;
    }
    pendingMascotLookPointer = { x: event.clientX, y: event.clientY };
    if (mascotLookFrameId !== null) {
      return;
    }
    mascotLookFrameId = window.requestAnimationFrame(() => {
      mascotLookFrameId = null;
      updateMascotLookFromPointer();
    });
  }

  function updateMascotLookFromPointer() {
    const pointer = pendingMascotLookPointer;
    const element = avatarElement.value;
    if (!pointer || !element) {
      return;
    }

    const bounds = element.getBoundingClientRect();
    const centerX = bounds.left + bounds.width / 2;
    const centerY = bounds.top + bounds.height / 2;
    const deltaX = pointer.x - centerX;
    const deltaY = pointer.y - centerY;
    const distance = Math.hypot(deltaX, deltaY);
    if (distance < 1) {
      mascotLook.value = { x: 0, y: 0 };
      return;
    }
    mascotLook.value = { x: deltaX / distance, y: deltaY / distance };
  }

  function updateMascotLookFromVirtualCursor() {
    const buddyCenter = resolveBoxCenter(position.value, DEFAULT_BUDDY_SIZE);
    const cursorCenter = resolveBoxCenter(resolveCurrentVirtualCursorTrackingPosition(), BUDDY_VIRTUAL_CURSOR_SIZE);
    const deltaX = cursorCenter.x - buddyCenter.x;
    const deltaY = cursorCenter.y - buddyCenter.y;
    const distance = Math.hypot(deltaX, deltaY);
    if (distance < 1) {
      mascotLook.value = { x: 0, y: 0 };
      return;
    }
    mascotLook.value = { x: deltaX / distance, y: deltaY / distance };
  }

  function cancelMascotLookFrame() {
    if (mascotLookFrameId === null) {
      return;
    }
    window.cancelAnimationFrame(mascotLookFrameId);
    mascotLookFrameId = null;
  }

  function scheduleBuddyRoam() {
    if (!canBuddyRoam.value || buddyRoamTimerId !== null || buddyRoamTargetPosition !== null || mascotMotion.value !== "idle") {
      return;
    }
    buddyRoamTimerId = window.setTimeout(
      runBuddyIdleAnimation,
      randomBetween(BUDDY_IDLE_ANIMATION_MIN_DELAY_MS, BUDDY_IDLE_ANIMATION_MAX_DELAY_MS),
    );
  }

  function runBuddyIdleAnimation() {
    buddyRoamTimerId = null;
    if (!canBuddyRoam.value) {
      return;
    }
    buddyRoamSequenceId += 1;
    const action = chooseBuddyIdleAnimationAction();
    switch (action) {
      case "tail-switch":
        runBuddyIdleTailSwitch(buddyRoamSequenceId);
        break;
      case "random-move":
        runBuddyIdleRoam(buddyRoamSequenceId);
        break;
      case "virtual-cursor-orbit":
        runBuddyIdleVirtualCursorOrbit(buddyRoamSequenceId);
        break;
      case "virtual-cursor-chase":
        runBuddyIdleVirtualCursorChase(buddyRoamSequenceId);
        break;
    }
  }

  function runBuddyIdleTailSwitch(sequenceId: number) {
    tailSwitchNonce.value += 1;
    buddyRoamMotionTimerId = window.setTimeout(() => {
      buddyRoamMotionTimerId = null;
      finishBuddyIdleAnimation(sequenceId);
    }, BUDDY_IDLE_TAIL_SWITCH_DURATION_MS);
  }

  function finishBuddyIdleAnimation(sequenceId: number) {
    if (sequenceId !== buddyRoamSequenceId) {
      return;
    }
    scheduleBuddyRoam();
  }

  function runBuddyIdleRoam(sequenceId: number, options: BuddyIdleRunOptions = {}) {
    if (sequenceId !== buddyRoamSequenceId) {
      return;
    }
    buddyRoamTargetPosition = resolveBuddyRoamTargetPosition(position.value, viewport.value);
    runBuddyRoamStep(sequenceId, options);
  }

  function runBuddyRoamStep(sequenceId: number, options: BuddyIdleRunOptions = {}) {
    if (sequenceId !== buddyRoamSequenceId) {
      return;
    }
    const targetPosition = buddyRoamTargetPosition;
    if (!canRunBuddyIdleAnimation(options) || targetPosition === null) {
      finishBuddyRoamSequence(false);
      return;
    }

    const nextPosition = resolveBuddyRoamStepPosition(position.value, targetPosition, viewport.value);
    const motionDurationMs = resolveMascotMoveDurationMs(motionConfig.value.moveDurationMs, "random");
    mascotMoveDurationMs.value = motionDurationMs;
    restartAvatarHopAnimation();
    mascotFacing.value = resolveBuddyRoamFacing(nextPosition.x - position.value.x);
    mascotMotion.value = "roam";
    position.value = nextPosition;
    buddyRoamMotionTimerId = window.setTimeout(() => {
      if (sequenceId !== buddyRoamSequenceId) {
        return;
      }
      buddyRoamMotionTimerId = null;
      mascotMotion.value = "idle";
      if (!canRunBuddyIdleAnimation(options)) {
        finishBuddyRoamSequence(false);
        return;
      }
      if (isBuddyRoamTargetReached(position.value, targetPosition)) {
        finishBuddyRoamSequence(true);
        return;
      }
      buddyRoamStepTimerId = window.setTimeout(() => {
        buddyRoamStepTimerId = null;
        runBuddyRoamStep(sequenceId, options);
      }, motionConfig.value.stepPauseMs);
    }, motionDurationMs);
  }

  function runBuddyIdleVirtualCursorOrbit(sequenceId: number, options: BuddyIdleRunOptions = {}) {
    if (sequenceId !== buddyRoamSequenceId || !canRunBuddyIdleAnimation(options)) {
      return;
    }
    cancelBuddyVirtualCursorIdleFrame();
    virtualCursorIdleActionMode.value = "orbit";
    virtualCursorPickupPending = true;
    setVirtualCursorEnabled(true);
    scheduleVirtualCursorIdleActionStart(sequenceId, () => {
      runBuddyIdleVirtualCursorOrbitFrame(
        sequenceId,
        performance.now(),
        resolveVirtualCursorOrbitAngle(virtualCursorPosition.value, position.value),
      );
    });
  }

  function runBuddyIdleVirtualCursorOrbitFrame(sequenceId: number, startedAtMs: number, startAngle: number) {
    if (sequenceId !== buddyRoamSequenceId || virtualCursorIdleActionMode.value !== "orbit") {
      cancelBuddyVirtualCursorIdleFrame();
      return;
    }
    const elapsedMs = performance.now() - startedAtMs;
    const progress = Math.min(1, elapsedMs / BUDDY_IDLE_VIRTUAL_CURSOR_ORBIT_LAP_DURATION_MS);
    const angle = startAngle + progress * Math.PI * 2;
    moveVirtualCursorTo(resolveVirtualCursorOrbitPosition(angle, position.value, viewport.value), {
      angleDeg: resolveVirtualCursorOrbitTangentAngle(angle),
      durationMs: 0,
      rotateDurationMs: 0,
    });
    updateMascotLookFromVirtualCursor();
    if (progress >= 1) {
      buddyVirtualCursorIdleFrameId = null;
      setVirtualCursorMoveTransitionDuration(BUDDY_VIRTUAL_CURSOR_MOVE_TRANSITION_MS);
      if (Math.random() < 0.5) {
        settleVirtualCursorRotation();
        finishBuddyIdleVirtualCursorAction(sequenceId);
        return;
      }
      runBuddyIdleVirtualCursorOrbitFrame(sequenceId, performance.now(), startAngle);
      return;
    }
    buddyVirtualCursorIdleFrameId = window.requestAnimationFrame(() => runBuddyIdleVirtualCursorOrbitFrame(sequenceId, startedAtMs, startAngle));
  }

  function runBuddyIdleVirtualCursorChase(sequenceId: number, options: BuddyIdleRunOptions = {}) {
    if (sequenceId !== buddyRoamSequenceId || !canRunBuddyIdleAnimation(options)) {
      return;
    }
    virtualCursorIdleActionMode.value = "chase";
    virtualCursorPickupPending = true;
    setVirtualCursorEnabled(true);
    scheduleVirtualCursorIdleActionStart(sequenceId, () => {
      moveBuddyIdleVirtualCursorChaseTarget(sequenceId);
    });
  }

  function scheduleVirtualCursorIdleActionStart(sequenceId: number, callback: () => void) {
    const delayMs = virtualCursorPhase.value === "active"
      ? BUDDY_VIRTUAL_CURSOR_READY_FRAME_DELAY_MS
      : BUDDY_VIRTUAL_CURSOR_MORPH_DURATION_MS + BUDDY_VIRTUAL_CURSOR_READY_FRAME_DELAY_MS;
    buddyRoamMotionTimerId = window.setTimeout(() => {
      buddyRoamMotionTimerId = null;
      if (sequenceId !== buddyRoamSequenceId || virtualCursorIdleActionMode.value === "none") {
        return;
      }
      if (virtualCursorPhase.value !== "active") {
        if (virtualCursorEnabled.value && virtualCursorPhase.value === "launching") {
          scheduleVirtualCursorIdleActionStart(sequenceId, callback);
        }
        return;
      }
      callback();
    }, delayMs);
  }

  function moveBuddyIdleVirtualCursorChaseTarget(sequenceId: number) {
    if (sequenceId !== buddyRoamSequenceId || virtualCursorIdleActionMode.value !== "chase") {
      return;
    }
    cancelBuddyVirtualCursorIdleFrame();
    const targetPosition = resolveCurrentRandomVirtualCursorChasePosition();
    const flightDurationMs = resolveVirtualCursorMoveDurationMs(
      virtualCursorPosition.value,
      targetPosition,
      motionConfig.value.virtualCursorFlightSpeedPxPerS,
    );
    const flightWaitMs = moveVirtualCursorToWithArmedTransition(targetPosition, { durationMs: flightDurationMs });
    buddyRoamMotionTimerId = window.setTimeout(() => {
      buddyRoamMotionTimerId = null;
      if (sequenceId !== buddyRoamSequenceId || virtualCursorIdleActionMode.value !== "chase") {
        return;
      }
      clearVirtualCursorFlightTracking();
      runBuddyIdleVirtualCursorChaseLoop(sequenceId, targetPosition, performance.now());
    }, flightWaitMs);
  }

  function runBuddyIdleVirtualCursorChaseLoop(sequenceId: number, centerPosition: BuddyPosition, startedAtMs: number) {
    if (sequenceId !== buddyRoamSequenceId || virtualCursorIdleActionMode.value !== "chase") {
      cancelBuddyVirtualCursorIdleFrame();
      return;
    }
    const elapsedMs = performance.now() - startedAtMs;
    const progress = (elapsedMs % BUDDY_IDLE_VIRTUAL_CURSOR_CHASE_LOOP_PERIOD_MS) / BUDDY_IDLE_VIRTUAL_CURSOR_CHASE_LOOP_PERIOD_MS;
    const angle = progress * Math.PI * 2;
    moveVirtualCursorTo(resolveVirtualCursorChaseLoopPosition(angle, centerPosition, viewport.value), {
      angleDeg: resolveVirtualCursorChaseLoopTangentAngle(angle),
      durationMs: 0,
      rotateDurationMs: 0,
    });
    updateMascotLookFromVirtualCursor();
    requestBuddyFollowVirtualCursor();
    buddyVirtualCursorIdleFrameId = window.requestAnimationFrame(() => runBuddyIdleVirtualCursorChaseLoop(sequenceId, centerPosition, startedAtMs));
  }

  function finishBuddyIdleVirtualCursorAction(sequenceId: number) {
    if (sequenceId !== buddyRoamSequenceId) {
      return;
    }
    pickupVirtualCursor({ sequenceId, finishIdleAnimation: true });
  }

  function pickupVirtualCursor(options: { sequenceId?: number; finishIdleAnimation?: boolean } = {}) {
    const sequenceId = options.sequenceId ?? buddyRoamSequenceId;
    cancelBuddyVirtualCursorIdleFrame();
    virtualCursorIdleActionMode.value = "none";
    virtualCursorPickupPending = false;
    setVirtualCursorEnabled(false);
    if (!options.finishIdleAnimation) {
      return;
    }
    if (buddyRoamMotionTimerId !== null) {
      window.clearTimeout(buddyRoamMotionTimerId);
    }
    buddyRoamMotionTimerId = window.setTimeout(() => {
      buddyRoamMotionTimerId = null;
      finishBuddyIdleAnimation(sequenceId);
    }, BUDDY_VIRTUAL_CURSOR_MORPH_DURATION_MS + 80);
  }

  function resolveCurrentRandomVirtualCursorChasePosition(): BuddyPosition {
    return resolveRandomVirtualCursorChasePositionFromModel(
      position.value,
      viewport.value,
      resolveVirtualCursorFollowMaxDistancePx(),
    );
  }

  function finishBuddyRoamSequence(shouldPersistPosition: boolean) {
    buddyRoamTargetPosition = null;
    mascotMotion.value = "idle";
    mascotFacing.value = "front";
    if (shouldPersistPosition) {
      persistPosition();
    }
    scheduleBuddyRoam();
  }

  function cancelBuddyRoamTimers() {
    buddyRoamSequenceId += 1;
    cancelBuddyVirtualCursorIdleFrame();
    if (buddyRoamTimerId !== null) {
      window.clearTimeout(buddyRoamTimerId);
      buddyRoamTimerId = null;
    }
    if (buddyRoamMotionTimerId !== null) {
      window.clearTimeout(buddyRoamMotionTimerId);
      buddyRoamMotionTimerId = null;
    }
    if (buddyRoamStepTimerId !== null) {
      window.clearTimeout(buddyRoamStepTimerId);
      buddyRoamStepTimerId = null;
    }
    buddyRoamTargetPosition = null;
    virtualCursorIdleActionMode.value = "none";
    mascotMotion.value = "idle";
    mascotFacing.value = "front";
  }

  function cancelBuddyVirtualCursorIdleFrame() {
    if (buddyVirtualCursorIdleFrameId !== null) {
      window.cancelAnimationFrame(buddyVirtualCursorIdleFrameId);
      buddyVirtualCursorIdleFrameId = null;
    }
    clearVirtualCursorFlightFrame();
    virtualCursorAngleFrameTimestampMs = null;
    setVirtualCursorMoveTransitionDuration(BUDDY_VIRTUAL_CURSOR_MOVE_TRANSITION_MS);
    setVirtualCursorRotateTransitionDuration(BUDDY_VIRTUAL_CURSOR_ROTATE_TRANSITION_MS);
  }

  function clearVirtualCursorFlightFrame() {
    if (virtualCursorFlightFrameId !== null && typeof window !== "undefined") {
      window.cancelAnimationFrame(virtualCursorFlightFrameId);
    }
    virtualCursorFlightFrameId = null;
    clearVirtualCursorFlightTracking();
  }

  function clearVirtualCursorFlightTracking() {
    if (virtualCursorFlightTrackingFrameId !== null && typeof window !== "undefined") {
      window.cancelAnimationFrame(virtualCursorFlightTrackingFrameId);
    }
    virtualCursorFlightTrackingFrameId = null;
    virtualCursorFlightTracking = null;
    virtualCursorTrackingPosition = null;
  }

  function requestBuddyFollowVirtualCursor() {
    if (!shouldBuddyFollowVirtualCursor.value || virtualCursorPhase.value !== "active" || isPanelFullscreen.value) {
      return;
    }
    const targetPosition = resolveCurrentBuddyVirtualCursorFollowTargetPosition();
    const isFollowingMotionActive = buddyVirtualCursorFollowMotionTimerId !== null;
    if (isBuddyVirtualCursorFollowTargetReached(position.value, targetPosition)) {
      if (isFollowingMotionActive) {
        buddyVirtualCursorFollowTargetPosition = targetPosition;
        return;
      }
      if (
        buddyVirtualCursorFollowTargetPosition !== null ||
        buddyVirtualCursorFollowStepTimerId !== null
      ) {
        finishBuddyVirtualCursorFollowSequence(true);
      }
      return;
    }

    const wasFollowing =
      buddyVirtualCursorFollowTargetPosition !== null ||
      buddyVirtualCursorFollowMotionTimerId !== null ||
      buddyVirtualCursorFollowStepTimerId !== null;
    if (!wasFollowing && virtualCursorIdleActionMode.value === "none") {
      cancelBuddyRoamTimers();
    }
    buddyVirtualCursorFollowTargetPosition = targetPosition;
    if (wasFollowing) {
      return;
    }

    buddyVirtualCursorFollowSequenceId += 1;
    runBuddyVirtualCursorFollowStep(buddyVirtualCursorFollowSequenceId);
  }

  function runBuddyVirtualCursorFollowStep(sequenceId: number) {
    if (sequenceId !== buddyVirtualCursorFollowSequenceId) {
      return;
    }
    const targetPosition = buddyVirtualCursorFollowTargetPosition;
    if (!shouldBuddyFollowVirtualCursor.value || isPanelFullscreen.value || targetPosition === null) {
      finishBuddyVirtualCursorFollowSequence(false);
      return;
    }
    if (isBuddyVirtualCursorFollowTargetReached(position.value, targetPosition)) {
      finishBuddyVirtualCursorFollowSequence(true);
      return;
    }

    const nextPosition = resolveBuddyRoamStepPosition(position.value, targetPosition, viewport.value);
    const motionDurationMs = resolveMascotMoveDurationMs(motionConfig.value.moveDurationMs, "fixed");
    mascotMoveDurationMs.value = motionDurationMs;
    restartAvatarHopAnimation();
    mascotFacing.value = resolveBuddyRoamFacing(nextPosition.x - position.value.x);
    mascotMotion.value = "roam";
    position.value = nextPosition;
    updateMascotLookFromVirtualCursor();
    buddyVirtualCursorFollowMotionTimerId = window.setTimeout(() => {
      if (sequenceId !== buddyVirtualCursorFollowSequenceId) {
        return;
      }
      buddyVirtualCursorFollowMotionTimerId = null;
      mascotMotion.value = "idle";
      const latestTargetPosition = buddyVirtualCursorFollowTargetPosition;
      if (!shouldBuddyFollowVirtualCursor.value || isPanelFullscreen.value || latestTargetPosition === null) {
        finishBuddyVirtualCursorFollowSequence(false);
        return;
      }
      if (isBuddyVirtualCursorFollowTargetReached(position.value, latestTargetPosition)) {
        finishBuddyVirtualCursorFollowSequence(true);
        return;
      }
      buddyVirtualCursorFollowStepTimerId = window.setTimeout(() => {
        buddyVirtualCursorFollowStepTimerId = null;
        runBuddyVirtualCursorFollowStep(sequenceId);
      }, motionConfig.value.stepPauseMs);
    }, motionDurationMs);
  }

  function resolveCurrentBuddyVirtualCursorFollowTargetPosition(): BuddyPosition {
    return resolveBuddyVirtualCursorFollowTargetPositionFromModel(
      position.value,
      resolveCurrentVirtualCursorTrackingPosition(),
      viewport.value,
      resolveVirtualCursorFollowMaxDistancePx(),
    );
  }

  function finishBuddyVirtualCursorFollowSequence(shouldPersistPosition: boolean) {
    cancelBuddyVirtualCursorFollowTimers();
    cancelBuddyVirtualCursorIdleFrame();
    mascotMotion.value = "idle";
    mascotFacing.value = "front";
    if (shouldPersistPosition) {
      persistPosition();
    }
    if (virtualCursorPickupPending && virtualCursorIdleActionMode.value === "none" && virtualCursorEnabled.value) {
      pickupVirtualCursor({ finishIdleAnimation: true });
      return;
    }
    if (virtualCursorIdleActionMode.value === "chase") {
      if (Math.random() < 0.5) {
        pickupVirtualCursor({ sequenceId: buddyRoamSequenceId, finishIdleAnimation: true });
        return;
      }
      moveBuddyIdleVirtualCursorChaseTarget(buddyRoamSequenceId);
    }
  }

  function cancelBuddyVirtualCursorFollowTimers() {
    buddyVirtualCursorFollowSequenceId += 1;
    if (buddyVirtualCursorFollowMotionTimerId !== null) {
      window.clearTimeout(buddyVirtualCursorFollowMotionTimerId);
      buddyVirtualCursorFollowMotionTimerId = null;
    }
    if (buddyVirtualCursorFollowStepTimerId !== null) {
      window.clearTimeout(buddyVirtualCursorFollowStepTimerId);
      buddyVirtualCursorFollowStepTimerId = null;
    }
    buddyVirtualCursorFollowTargetPosition = null;
    mascotMotion.value = "idle";
    mascotFacing.value = "front";
  }

  function clearBuddyDebugActionTimer() {
    if (buddyDebugActionTimerId !== null) {
      window.clearTimeout(buddyDebugActionTimerId);
      buddyDebugActionTimerId = null;
    }
    debugDragging.value = false;
  }

  function restartAvatarHopAnimation() {
    avatarHopCycle.value += 1;
  }

  function playMascotDebugMotion(motion: BuddyMascotMotion, durationMs: number, facing: BuddyMascotFacing) {
    mood.value = "idle";
    mascotFacing.value = facing;
    mascotMoveDurationMs.value = durationMs;
    restartAvatarHopAnimation();
    mascotMotion.value = motion;
    buddyDebugActionTimerId = window.setTimeout(() => {
      mascotMotion.value = "idle";
      mascotFacing.value = "front";
      buddyDebugActionTimerId = null;
    }, durationMs);
  }

  function triggerMascotDebugAction(action: BuddyMascotDebugAction) {
    cancelBuddyRoamTimers();
    clearSpeakingIdleTimer();
    clearBuddyDebugActionTimer();
    switch (action) {
      case "idle":
        mood.value = "idle";
        mascotMotion.value = "idle";
        mascotFacing.value = "front";
        break;
      case "thinking":
        mood.value = "thinking";
        mascotMotion.value = "idle";
        mascotFacing.value = "front";
        break;
      case "speaking":
        mood.value = "speaking";
        mascotMotion.value = "idle";
        mascotFacing.value = "front";
        break;
      case "error":
        mood.value = "error";
        mascotMotion.value = "idle";
        mascotFacing.value = "front";
        break;
      case "tap":
        mood.value = "idle";
        tapNonce.value += 1;
        break;
      case "dragging":
        mood.value = "idle";
        debugDragging.value = true;
        buddyDebugActionTimerId = window.setTimeout(() => {
          debugDragging.value = false;
          buddyDebugActionTimerId = null;
        }, 1100);
        break;
      case "hop":
        playMascotDebugMotion("hop", resolveMascotMoveDurationMs(motionConfig.value.moveDurationMs, "random"), "front");
        break;
      case "roam":
        playMascotDebugMotion("roam", resolveMascotMoveDurationMs(motionConfig.value.moveDurationMs, "random"), "right");
        break;
      case "idle-tail-switch":
        runBuddyIdleTailSwitch(++buddyRoamSequenceId);
        break;
      case "idle-random-move":
        mood.value = "idle";
        runBuddyIdleRoam(++buddyRoamSequenceId, { force: true });
        break;
      case "idle-virtual-cursor-orbit":
        mood.value = "idle";
        runBuddyIdleVirtualCursorOrbit(++buddyRoamSequenceId, { force: true });
        break;
      case "idle-virtual-cursor-chase":
        mood.value = "idle";
        runBuddyIdleVirtualCursorChase(++buddyRoamSequenceId, { force: true });
        break;
      case "face-left":
        mood.value = "idle";
        mascotMotion.value = "idle";
        mascotFacing.value = "left";
        break;
      case "face-front":
        mood.value = "idle";
        mascotMotion.value = "idle";
        mascotFacing.value = "front";
        break;
      case "face-right":
        mood.value = "idle";
        mascotMotion.value = "idle";
        mascotFacing.value = "right";
        break;
    }
  }

  function canRunBuddyIdleAnimation(options: BuddyIdleRunOptions = {}) {
    return options.force || canBuddyRoam.value;
  }

  function startVirtualCursorLaunch() {
    clearVirtualCursorTransition();
    virtualCursorPhase.value = "launching";
    virtualCursorDetached.value = true;
    virtualCursorDragging.value = false;
    virtualCursorPosition.value = resolveDefaultVirtualCursorPosition(viewport.value, position.value);
    virtualCursorPath.value = VIRTUAL_CURSOR_STAR_PATH;
    virtualCursorAngleDeg.value = BUDDY_VIRTUAL_CURSOR_STAR_ANGLE_DEG;
    virtualCursorScale.value = BUDDY_VIRTUAL_CURSOR_DOCKED_SCALE;
    startVirtualCursorMorph(VIRTUAL_CURSOR_STAR_PATH, VIRTUAL_CURSOR_SHAPE_PATH);

    const targetPosition = resolveVirtualCursorLaunchPosition(viewport.value, position.value);
    if (typeof window === "undefined") {
      virtualCursorScale.value = BUDDY_VIRTUAL_CURSOR_ACTIVE_SCALE;
      moveVirtualCursorTo(targetPosition);
      finishVirtualCursorLaunch();
      return;
    }

    virtualCursorTransitionFrameId = window.requestAnimationFrame(() => {
      virtualCursorTransitionFrameId = null;
      virtualCursorScale.value = BUDDY_VIRTUAL_CURSOR_ACTIVE_SCALE;
      moveVirtualCursorTo(targetPosition);
    });
    virtualCursorTransitionTimerId = window.setTimeout(finishVirtualCursorLaunch, BUDDY_VIRTUAL_CURSOR_MORPH_DURATION_MS);
  }

  function finishVirtualCursorLaunch() {
    virtualCursorTransitionTimerId = null;
    virtualCursorPath.value = VIRTUAL_CURSOR_SHAPE_PATH;
    virtualCursorMorphAnimation.value = null;
    setVirtualCursorMoveTransitionDuration(BUDDY_VIRTUAL_CURSOR_MOVE_TRANSITION_MS);
    setVirtualCursorRotateTransitionDuration(BUDDY_VIRTUAL_CURSOR_ROTATE_TRANSITION_MS);
    if (!virtualCursorEnabled.value) {
      startVirtualCursorReturn();
      return;
    }
    virtualCursorPhase.value = "active";
    virtualCursorDetached.value = true;
    virtualCursorScale.value = BUDDY_VIRTUAL_CURSOR_ACTIVE_SCALE;
    settleVirtualCursorRotation();
    updateMascotLookFromVirtualCursor();
    requestBuddyFollowVirtualCursor();
  }

  function startVirtualCursorReturn() {
    clearVirtualCursorTransition();
    if (virtualCursorPhase.value === "hidden") {
      virtualCursorDetached.value = false;
      virtualCursorDragging.value = false;
      return;
    }

    virtualCursorPhase.value = "returning";
    virtualCursorDetached.value = true;
    virtualCursorDragging.value = false;
    virtualCursorScale.value = BUDDY_VIRTUAL_CURSOR_ACTIVE_SCALE;
    virtualCursorPath.value = VIRTUAL_CURSOR_SHAPE_PATH;
    startVirtualCursorMorph(VIRTUAL_CURSOR_SHAPE_PATH, VIRTUAL_CURSOR_STAR_PATH);

    const dockedPosition = resolveDefaultVirtualCursorPosition(viewport.value, position.value);
    if (typeof window === "undefined") {
      virtualCursorAngleDeg.value = BUDDY_VIRTUAL_CURSOR_STAR_ANGLE_DEG;
      virtualCursorScale.value = BUDDY_VIRTUAL_CURSOR_DOCKED_SCALE;
      moveVirtualCursorTo(dockedPosition, { updateAngle: false });
      finishVirtualCursorReturn();
      return;
    }

    virtualCursorTransitionFrameId = window.requestAnimationFrame(() => {
      virtualCursorTransitionFrameId = null;
      virtualCursorAngleDeg.value = BUDDY_VIRTUAL_CURSOR_STAR_ANGLE_DEG;
      virtualCursorScale.value = BUDDY_VIRTUAL_CURSOR_DOCKED_SCALE;
      moveVirtualCursorTo(dockedPosition, { updateAngle: false });
    });
    virtualCursorTransitionTimerId = window.setTimeout(finishVirtualCursorReturn, BUDDY_VIRTUAL_CURSOR_MORPH_DURATION_MS);
  }

  function finishVirtualCursorReturn() {
    virtualCursorTransitionTimerId = null;
    const dockedPosition = resolveDefaultVirtualCursorPosition(viewport.value, position.value);
    clearVirtualCursorFlightTracking();
    setVirtualCursorMoveTransitionDuration(BUDDY_VIRTUAL_CURSOR_MOVE_TRANSITION_MS);
    setVirtualCursorRotateTransitionDuration(BUDDY_VIRTUAL_CURSOR_ROTATE_TRANSITION_MS);
    virtualCursorPosition.value = dockedPosition;
    virtualCursorPath.value = VIRTUAL_CURSOR_STAR_PATH;
    virtualCursorMorphAnimation.value = null;
    virtualCursorPhase.value = "hidden";
    virtualCursorDetached.value = false;
    virtualCursorDragging.value = false;
    virtualCursorAngleDeg.value = BUDDY_VIRTUAL_CURSOR_STAR_ANGLE_DEG;
    virtualCursorScale.value = BUDDY_VIRTUAL_CURSOR_DOCKED_SCALE;
    mascotLook.value = { x: 0, y: 0 };
  }

  function startVirtualCursorMorph(fromPath: string, toPath: string) {
    virtualCursorMorphAnimationKey += 1;
    virtualCursorMorphAnimation.value = {
      key: virtualCursorMorphAnimationKey,
      values: `${fromPath};${toPath}`,
      durationMs: BUDDY_VIRTUAL_CURSOR_MORPH_DURATION_MS,
    };
    void nextTick(() => {
      virtualCursorAnimateElement.value?.beginElement();
    });
  }

  function clearVirtualCursorTransition() {
    clearVirtualCursorFlightFrame();
    if (virtualCursorTransitionFrameId !== null && typeof window !== "undefined") {
      window.cancelAnimationFrame(virtualCursorTransitionFrameId);
    }
    if (virtualCursorTransitionTimerId !== null && typeof window !== "undefined") {
      window.clearTimeout(virtualCursorTransitionTimerId);
    }
    virtualCursorTransitionFrameId = null;
    virtualCursorTransitionTimerId = null;
    virtualCursorMorphAnimation.value = null;
  }

  function moveVirtualCursorTo(
    nextPosition: BuddyPosition,
    options: { updateAngle?: boolean; durationMs?: number; rotateDurationMs?: number; angleDeg?: number; smoothAngle?: boolean } = {},
  ) {
    clearVirtualCursorFlightFrame();
    const currentPosition = virtualCursorPosition.value;
    const targetAngleDeg = options.angleDeg ?? resolveVirtualCursorFlightAngle(currentPosition, nextPosition);
    setVirtualCursorMoveTransitionDuration(
      options.durationMs ??
        resolveVirtualCursorMoveDurationMs(
          currentPosition,
          nextPosition,
          motionConfig.value.virtualCursorFlightSpeedPxPerS,
        ),
    );
    setVirtualCursorRotateTransitionDuration(
      options.rotateDurationMs ??
        resolveVirtualCursorRotateDurationMs(
          virtualCursorAngleDeg.value,
          targetAngleDeg,
          motionConfig.value.virtualCursorRotationSpeedDegPerS,
        ),
    );
    if (options.updateAngle !== false) {
      virtualCursorAngleDeg.value = options.smoothAngle
        ? resolveSmoothedVirtualCursorAngleForFrame(targetAngleDeg)
        : resolveContinuousVirtualCursorAngle(virtualCursorAngleDeg.value, targetAngleDeg);
    } else {
      virtualCursorAngleFrameTimestampMs = null;
    }
    virtualCursorPosition.value = nextPosition;
  }

  function moveVirtualCursorToWithArmedTransition(
    nextPosition: BuddyPosition,
    options: { updateAngle?: boolean; durationMs?: number; rotateDurationMs?: number; angleDeg?: number; smoothAngle?: boolean } = {},
  ) {
    const currentPosition = virtualCursorPosition.value;
    const targetAngleDeg = options.angleDeg ?? resolveVirtualCursorFlightAngle(currentPosition, nextPosition);
    const durationMs = options.durationMs ??
      resolveVirtualCursorMoveDurationMs(
        currentPosition,
        nextPosition,
        motionConfig.value.virtualCursorFlightSpeedPxPerS,
      );
    const rotateDurationMs = options.rotateDurationMs ??
      resolveVirtualCursorRotateDurationMs(
        virtualCursorAngleDeg.value,
        targetAngleDeg,
        motionConfig.value.virtualCursorRotationSpeedDegPerS,
      );
    clearVirtualCursorFlightFrame();
    setVirtualCursorMoveTransitionDuration(durationMs);
    setVirtualCursorRotateTransitionDuration(rotateDurationMs);

    const moveOptions = {
      ...options,
      durationMs,
      rotateDurationMs,
    };
    if (typeof window === "undefined") {
      moveVirtualCursorTo(nextPosition, moveOptions);
      startVirtualCursorFlightTracking(currentPosition, nextPosition, durationMs);
      return virtualCursorMoveDurationMs.value;
    }

    virtualCursorFlightFrameId = window.requestAnimationFrame(() => {
      virtualCursorFlightFrameId = null;
      moveVirtualCursorTo(nextPosition, moveOptions);
      startVirtualCursorFlightTracking(currentPosition, nextPosition, durationMs);
    });
    return virtualCursorMoveDurationMs.value + BUDDY_VIRTUAL_CURSOR_FLIGHT_SETTLE_MS;
  }

  function startVirtualCursorFlightTracking(fromPosition: BuddyPosition, toPosition: BuddyPosition, durationMs: number) {
    clearVirtualCursorFlightTracking();
    if (durationMs <= 0) {
      virtualCursorTrackingPosition = toPosition;
      updateMascotLookFromVirtualCursor();
      requestBuddyFollowVirtualCursor();
      virtualCursorTrackingPosition = null;
      return;
    }
    virtualCursorFlightTracking = {
      fromPosition,
      toPosition,
      startedAtMs: typeof performance === "undefined" ? Date.now() : performance.now(),
      durationMs,
    };
    runVirtualCursorFlightTrackingFrame();
  }

  function runVirtualCursorFlightTrackingFrame() {
    const tracking = virtualCursorFlightTracking;
    if (!tracking) {
      return;
    }
    const nowMs = typeof performance === "undefined" ? Date.now() : performance.now();
    const progress = Math.min(1, Math.max(0, (nowMs - tracking.startedAtMs) / tracking.durationMs));
    virtualCursorTrackingPosition = interpolateBuddyPosition(tracking.fromPosition, tracking.toPosition, progress);
    updateMascotLookFromVirtualCursor();
    requestBuddyFollowVirtualCursor();
    if (virtualCursorFlightTracking !== tracking) {
      virtualCursorFlightTrackingFrameId = null;
      return;
    }
    if (progress >= 1) {
      virtualCursorFlightTrackingFrameId = null;
      virtualCursorFlightTracking = null;
      virtualCursorTrackingPosition = null;
      return;
    }
    if (typeof window !== "undefined") {
      virtualCursorFlightTrackingFrameId = window.requestAnimationFrame(runVirtualCursorFlightTrackingFrame);
    }
  }

  function resolveCurrentVirtualCursorTrackingPosition() {
    return virtualCursorTrackingPosition ?? virtualCursorPosition.value;
  }

  function resolveVirtualCursorFollowMaxDistancePx() {
    return motionConfig.value.virtualCursorFollowMaxDistancePx;
  }

  function setVirtualCursorMoveTransitionDuration(durationMs: number) {
    virtualCursorMoveDurationMs.value = Math.round(clampNumber(durationMs, 0, BUDDY_VIRTUAL_CURSOR_MAX_FLIGHT_DURATION_MS));
  }

  function setVirtualCursorRotateTransitionDuration(durationMs: number) {
    virtualCursorRotateDurationMs.value = Math.round(clampNumber(durationMs, 0, BUDDY_VIRTUAL_CURSOR_MAX_ROTATE_TRANSITION_MS));
  }

  function settleVirtualCursorRotation() {
    setVirtualCursorRotateTransitionDuration(BUDDY_VIRTUAL_CURSOR_ROTATE_TRANSITION_MS);
    virtualCursorAngleFrameTimestampMs = null;
    virtualCursorAngleDeg.value = BUDDY_VIRTUAL_CURSOR_RESTING_ANGLE_DEG;
  }

  function resolveSmoothedVirtualCursorAngleForFrame(targetAngleDeg: number) {
    const nowMs = typeof performance === "undefined" ? Date.now() : performance.now();
    const elapsedMs = virtualCursorAngleFrameTimestampMs === null ? 16 : Math.max(0, nowMs - virtualCursorAngleFrameTimestampMs);
    virtualCursorAngleFrameTimestampMs = nowMs;
    return resolveSmoothedVirtualCursorAngle(
      virtualCursorAngleDeg.value,
      targetAngleDeg,
      elapsedMs,
      motionConfig.value.virtualCursorRotationSpeedDegPerS,
    );
  }

  async function moveVirtualCursorToElement(element: HTMLElement) {
    const cursorPosition = resolveVirtualCursorPositionForElement(element);
    const flightWaitMs = moveVirtualCursorToWithArmedTransition(cursorPosition);
    await waitForVirtualOperation(flightWaitMs);
  }

  function moveVirtualCursorToClientPoint(point: BuddyPosition, options: { durationMs?: number } = {}) {
    return moveVirtualCursorToWithArmedTransition(resolveVirtualCursorPositionForClientPoint(point, viewport.value), options);
  }

  async function ensureVirtualCursorReadyForOperation() {
    if (!virtualCursorEnabled.value) {
      setVirtualCursorEnabled(true);
    }
    if (virtualCursorPhase.value !== "active") {
      await waitForVirtualOperation(BUDDY_VIRTUAL_CURSOR_MORPH_DURATION_MS + BUDDY_VIRTUAL_CURSOR_READY_FRAME_DELAY_MS);
    }
  }

  function resolveVirtualCursorPositionForElement(element: HTMLElement): BuddyPosition {
    return resolveVirtualCursorPositionForClientPoint(resolveElementCenterPoint(element), viewport.value);
  }

  async function replaceVirtualText(element: HTMLInputElement | HTMLTextAreaElement, text: string) {
    const token = activeVirtualOperationToken.value;
    if (element.value) {
      while (element.value && !isVirtualOperationInterrupted(token)) {
        element.value = element.value.slice(0, -1);
        dispatchVirtualInputEvents(element, "deleteContentBackward", "");
        await waitForVirtualOperation(BUDDY_VIRTUAL_OPERATION_TYPE_CHARACTER_DELAY_MS);
      }
    }
    if (isVirtualOperationInterrupted(token)) {
      return;
    }
    await typeVirtualText(element, text);
  }

  async function typeVirtualText(element: HTMLInputElement | HTMLTextAreaElement, text: string) {
    const token = activeVirtualOperationToken.value;
    for (const character of text) {
      if (isVirtualOperationInterrupted(token)) {
        break;
      }
      element.value = `${element.value}${character}`;
      dispatchVirtualInputEvents(element, "insertText", character);
      await waitForVirtualOperation(BUDDY_VIRTUAL_OPERATION_TYPE_CHARACTER_DELAY_MS);
    }
  }

  function stopBuddyIdleAnimation(options: { closeVirtualCursor?: boolean } = {}) {
    cancelBuddyRoamTimers();
    cancelBuddyVirtualCursorFollowTimers();
    clearBuddyDebugActionTimer();
    virtualCursorIdleActionMode.value = "none";
    virtualCursorPickupPending = false;
    if (options.closeVirtualCursor) {
      const wasVirtualCursorEnabled = virtualCursorEnabled.value;
      setVirtualCursorEnabled(false);
      if (!wasVirtualCursorEnabled && virtualCursorPhase.value !== "hidden") {
        startVirtualCursorReturn();
      }
    }
  }

  function cancelBuddyRoamUnlessVirtualCursorIdle() {
    if (virtualCursorIdleActionMode.value !== "none") {
      return;
    }
    cancelBuddyRoamTimers();
  }

  function syncVirtualCursorAfterViewportResize() {
    virtualCursorPosition.value = clampBuddyPosition(
      virtualCursorPosition.value,
      viewport.value,
      BUDDY_VIRTUAL_CURSOR_SIZE,
      DEFAULT_BUDDY_MARGIN,
    );
    if (isVirtualCursorRendered.value) {
      updateMascotLookFromVirtualCursor();
      requestBuddyFollowVirtualCursor();
    }
  }

  function disposeBuddyMascotMotionController() {
    clearVirtualCursorDrag();
    clearBuddyDebugActionTimer();
    cancelBuddyRoamTimers();
    cancelBuddyVirtualCursorFollowTimers();
    cancelBuddyVirtualCursorIdleFrame();
    clearVirtualCursorTransition();
    cancelMascotLookFrame();
  }

  return {
    activateVirtualCursor,
    avatarElement,
    avatarHopCycle,
    canBuddyRoam,
    cancelBuddyRoamUnlessVirtualCursorIdle,
    cancelBuddyRoamTimers,
    clearBuddyDebugActionTimer,
    clearVirtualCursorDrag,
    clearVirtualCursorTransition,
    deactivateVirtualCursor,
    disposeBuddyMascotMotionController,
    ensureVirtualCursorReadyForOperation,
    handleMascotLookPointerMove,
    handleVirtualCursorPointerDown,
    isMascotDragging,
    isVirtualCursorRendered,
    mascotFacing,
    mascotLook,
    mascotMotion,
    mascotMoveDurationMs,
    moveVirtualCursorToClientPoint,
    moveVirtualCursorToElement,
    replaceVirtualText,
    requestBuddyFollowVirtualCursor,
    scheduleBuddyRoam,
    shouldFloatVirtualCursor,
    stopBuddyIdleAnimation,
    syncVirtualCursorAfterViewportResize,
    tailSwitchNonce,
    triggerMascotDebugAction,
    updateMascotLookFromVirtualCursor,
    virtualCursorAnimateElement,
    virtualCursorDetached,
    virtualCursorDragging,
    virtualCursorMorphAnimation,
    virtualCursorPath,
    virtualCursorPhase,
    virtualCursorStyle,
  };
}

function clampNumber(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

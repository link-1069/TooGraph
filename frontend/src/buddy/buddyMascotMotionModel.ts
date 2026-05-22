import {
  DEFAULT_BUDDY_MARGIN,
  DEFAULT_BUDDY_SIZE,
  clampBuddyPosition,
  type BuddyPosition,
  type BuddyViewport,
} from "./buddyPosition.ts";
import {
  BUDDY_VIRTUAL_CURSOR_SIZE,
  clampVirtualCursorFramePosition,
  resolveBoxCenter,
  resolveVirtualCursorFollowTargetDistancePx,
  resolveVirtualCursorVectorAngle,
} from "./buddyVirtualCursorGeometry.ts";

export type BuddyMascotFacing = "front" | "left" | "right";
export type BuddyIdleAnimationAction = "tail-switch" | "random-move" | "virtual-cursor-orbit" | "virtual-cursor-chase";
export type BuddyMascotMoveDurationMode = "fixed" | "random";

export const BUDDY_IDLE_ANIMATION_MIN_DELAY_MS = 5000;
export const BUDDY_IDLE_ANIMATION_MAX_DELAY_MS = 10000;
export const BUDDY_IDLE_ANIMATION_ACTIONS: BuddyIdleAnimationAction[] = [
  "tail-switch",
  "random-move",
  "virtual-cursor-orbit",
  "virtual-cursor-chase",
];
export const BUDDY_IDLE_TAIL_SWITCH_DURATION_MS = 1000;
export const BUDDY_IDLE_VIRTUAL_CURSOR_ORBIT_LAP_DURATION_MS = 1200;
export const BUDDY_IDLE_VIRTUAL_CURSOR_ORBIT_RADIUS_PX = DEFAULT_BUDDY_SIZE.width * 0.68;
export const BUDDY_ROAM_STEP_DISTANCE_PX = DEFAULT_BUDDY_SIZE.width;
export const BUDDY_ROAM_TARGET_MIN_DISTANCE_PX = DEFAULT_BUDDY_SIZE.width;
export const BUDDY_ROAM_TARGET_MAX_DISTANCE_PX = DEFAULT_BUDDY_SIZE.width * 3;
export const BUDDY_ROAM_TARGET_REACHED_DISTANCE_PX = 1;
export const BUDDY_IDLE_VIRTUAL_CURSOR_CHASE_LOOP_PERIOD_MS = 1600;
export const BUDDY_IDLE_VIRTUAL_CURSOR_CHASE_LOOP_RADIUS_PX = BUDDY_VIRTUAL_CURSOR_SIZE.width * 0.86;
export const BUDDY_IDLE_VIRTUAL_CURSOR_CHASE_LOOP_Y_RADIUS_PX = BUDDY_IDLE_VIRTUAL_CURSOR_CHASE_LOOP_RADIUS_PX * 0.62;
export const BUDDY_VIRTUAL_CURSOR_FOLLOW_TARGET_REACHED_DISTANCE_PX = 12;

export function randomBetween(min: number, max: number, random = Math.random) {
  if (max <= min) {
    return min;
  }
  return min + random() * (max - min);
}

export function resolveMascotMoveDurationMs(
  baseDurationMs: number,
  mode: BuddyMascotMoveDurationMode,
  random = Math.random,
) {
  if (mode === "fixed") {
    return baseDurationMs;
  }
  return Math.round(randomBetween(baseDurationMs, baseDurationMs * 2, random));
}

export function chooseBuddyIdleAnimationAction(random = Math.random): BuddyIdleAnimationAction {
  return BUDDY_IDLE_ANIMATION_ACTIONS[
    Math.floor(random() * BUDDY_IDLE_ANIMATION_ACTIONS.length)
  ] ?? "tail-switch";
}

export function resolveVirtualCursorOrbitPosition(
  angle: number,
  buddyPosition: BuddyPosition,
  viewport: BuddyViewport,
): BuddyPosition {
  const buddyCenter = resolveBoxCenter(buddyPosition, DEFAULT_BUDDY_SIZE);
  return clampVirtualCursorFramePosition(
    {
      x: buddyCenter.x + Math.cos(angle) * BUDDY_IDLE_VIRTUAL_CURSOR_ORBIT_RADIUS_PX - BUDDY_VIRTUAL_CURSOR_SIZE.width / 2,
      y: buddyCenter.y + Math.sin(angle) * BUDDY_IDLE_VIRTUAL_CURSOR_ORBIT_RADIUS_PX - BUDDY_VIRTUAL_CURSOR_SIZE.height / 2,
    },
    viewport,
  );
}

export function resolveVirtualCursorOrbitAngle(cursorPosition: BuddyPosition, buddyPosition: BuddyPosition) {
  const buddyCenter = resolveBoxCenter(buddyPosition, DEFAULT_BUDDY_SIZE);
  const cursorCenter = resolveBoxCenter(cursorPosition, BUDDY_VIRTUAL_CURSOR_SIZE);
  return Math.atan2(cursorCenter.y - buddyCenter.y, cursorCenter.x - buddyCenter.x);
}

export function resolveVirtualCursorOrbitTangentAngle(angle: number) {
  return resolveVirtualCursorVectorAngle(-Math.sin(angle), Math.cos(angle));
}

export function resolveVirtualCursorChaseLoopPosition(
  angle: number,
  centerPosition: BuddyPosition,
  viewport: BuddyViewport,
): BuddyPosition {
  return clampVirtualCursorFramePosition(
    {
      x: centerPosition.x + Math.sin(angle) * BUDDY_IDLE_VIRTUAL_CURSOR_CHASE_LOOP_RADIUS_PX,
      y: centerPosition.y + Math.sin(angle * 2) * BUDDY_IDLE_VIRTUAL_CURSOR_CHASE_LOOP_Y_RADIUS_PX,
    },
    viewport,
  );
}

export function resolveVirtualCursorChaseLoopTangentAngle(angle: number) {
  return resolveVirtualCursorVectorAngle(
    Math.cos(angle) * BUDDY_IDLE_VIRTUAL_CURSOR_CHASE_LOOP_RADIUS_PX,
    Math.cos(angle * 2) * BUDDY_IDLE_VIRTUAL_CURSOR_CHASE_LOOP_Y_RADIUS_PX * 2,
  );
}

export function resolveRandomVirtualCursorChasePosition(
  buddyPosition: BuddyPosition,
  viewport: BuddyViewport,
  followMaxDistancePx: number,
  random = Math.random,
): BuddyPosition {
  const buddyCenter = resolveBoxCenter(buddyPosition, DEFAULT_BUDDY_SIZE);
  const chaseLoopHorizontalMarginPx = DEFAULT_BUDDY_MARGIN + BUDDY_IDLE_VIRTUAL_CURSOR_CHASE_LOOP_RADIUS_PX;
  const chaseLoopVerticalMarginPx = DEFAULT_BUDDY_MARGIN + BUDDY_IDLE_VIRTUAL_CURSOR_CHASE_LOOP_Y_RADIUS_PX;
  const chaseLoopSafeMarginPx = Math.max(chaseLoopHorizontalMarginPx, chaseLoopVerticalMarginPx);
  for (let attempt = 0; attempt < 12; attempt += 1) {
    const candidate = clampBuddyPosition(
      {
        x: randomBetween(chaseLoopHorizontalMarginPx, Math.max(chaseLoopHorizontalMarginPx, viewport.width - BUDDY_VIRTUAL_CURSOR_SIZE.width - chaseLoopHorizontalMarginPx), random),
        y: randomBetween(chaseLoopVerticalMarginPx, Math.max(chaseLoopVerticalMarginPx, viewport.height - BUDDY_VIRTUAL_CURSOR_SIZE.height - chaseLoopVerticalMarginPx), random),
      },
      viewport,
      BUDDY_VIRTUAL_CURSOR_SIZE,
      chaseLoopSafeMarginPx,
    );
    const candidateCenter = resolveBoxCenter(candidate, BUDDY_VIRTUAL_CURSOR_SIZE);
    if (Math.hypot(candidateCenter.x - buddyCenter.x, candidateCenter.y - buddyCenter.y) > followMaxDistancePx * 1.15) {
      return candidate;
    }
  }
  const horizontalDirection = buddyCenter.x > viewport.width / 2 ? -1 : 1;
  const verticalDirection = buddyCenter.y > viewport.height / 2 ? -1 : 1;
  return clampBuddyPosition(
    {
      x: buddyCenter.x + horizontalDirection * followMaxDistancePx * 1.3 - BUDDY_VIRTUAL_CURSOR_SIZE.width / 2,
      y: buddyCenter.y + verticalDirection * followMaxDistancePx * 0.9 - BUDDY_VIRTUAL_CURSOR_SIZE.height / 2,
    },
    viewport,
    BUDDY_VIRTUAL_CURSOR_SIZE,
    chaseLoopSafeMarginPx,
  );
}

export function resolveBuddyRoamTargetPosition(
  currentPosition: BuddyPosition,
  viewport: BuddyViewport,
  random = Math.random,
): BuddyPosition {
  for (let attempt = 0; attempt < 12; attempt += 1) {
    const distance = randomBetween(BUDDY_ROAM_TARGET_MIN_DISTANCE_PX, BUDDY_ROAM_TARGET_MAX_DISTANCE_PX, random);
    const angle = randomBetween(0, Math.PI * 2, random);
    const candidate = clampBuddyPosition(
      {
        x: currentPosition.x + Math.cos(angle) * distance,
        y: currentPosition.y + Math.sin(angle) * distance,
      },
      viewport,
      DEFAULT_BUDDY_SIZE,
      DEFAULT_BUDDY_MARGIN,
    );
    if (Math.hypot(candidate.x - currentPosition.x, candidate.y - currentPosition.y) >= BUDDY_ROAM_TARGET_MIN_DISTANCE_PX) {
      return candidate;
    }
  }

  const horizontalDirection = currentPosition.x > viewport.width / 2 ? -1 : 1;
  const verticalDirection = currentPosition.y > viewport.height / 2 ? -0.35 : 0.35;
  return clampBuddyPosition(
    {
      x: currentPosition.x + horizontalDirection * BUDDY_ROAM_TARGET_MIN_DISTANCE_PX,
      y: currentPosition.y + verticalDirection * BUDDY_ROAM_TARGET_MIN_DISTANCE_PX,
    },
    viewport,
    DEFAULT_BUDDY_SIZE,
    DEFAULT_BUDDY_MARGIN,
  );
}

export function resolveBuddyRoamStepPosition(
  currentPosition: BuddyPosition,
  targetPosition: BuddyPosition,
  viewport: BuddyViewport,
): BuddyPosition {
  const deltaX = targetPosition.x - currentPosition.x;
  const deltaY = targetPosition.y - currentPosition.y;
  const distance = Math.hypot(deltaX, deltaY);
  if (distance <= BUDDY_ROAM_STEP_DISTANCE_PX) {
    return targetPosition;
  }
  return clampBuddyPosition(
    {
      x: currentPosition.x + (deltaX / distance) * BUDDY_ROAM_STEP_DISTANCE_PX,
      y: currentPosition.y + (deltaY / distance) * BUDDY_ROAM_STEP_DISTANCE_PX,
    },
    viewport,
    DEFAULT_BUDDY_SIZE,
    DEFAULT_BUDDY_MARGIN,
  );
}

export function resolveBuddyRoamFacing(deltaX: number): BuddyMascotFacing {
  if (Math.abs(deltaX) < 2) {
    return "front";
  }
  return deltaX < 0 ? "left" : "right";
}

export function isBuddyRoamTargetReached(currentPosition: BuddyPosition, targetPosition: BuddyPosition) {
  return Math.hypot(targetPosition.x - currentPosition.x, targetPosition.y - currentPosition.y) <= BUDDY_ROAM_TARGET_REACHED_DISTANCE_PX;
}

export function isBuddyVirtualCursorFollowTargetReached(currentPosition: BuddyPosition, targetPosition: BuddyPosition) {
  return Math.hypot(targetPosition.x - currentPosition.x, targetPosition.y - currentPosition.y) <= BUDDY_VIRTUAL_CURSOR_FOLLOW_TARGET_REACHED_DISTANCE_PX;
}

export function resolveBuddyVirtualCursorFollowTargetPosition(
  buddyPosition: BuddyPosition,
  cursorPosition: BuddyPosition,
  viewport: BuddyViewport,
  followMaxDistancePx: number,
): BuddyPosition {
  const buddyCenter = resolveBoxCenter(buddyPosition, DEFAULT_BUDDY_SIZE);
  const cursorCenter = resolveBoxCenter(cursorPosition, BUDDY_VIRTUAL_CURSOR_SIZE);
  const deltaX = buddyCenter.x - cursorCenter.x;
  const deltaY = buddyCenter.y - cursorCenter.y;
  const distance = Math.hypot(deltaX, deltaY);
  if (distance <= followMaxDistancePx) {
    return buddyPosition;
  }

  const unitX = distance < 1 ? -0.82 : deltaX / distance;
  const unitY = distance < 1 ? 0.58 : deltaY / distance;
  const followTargetDistancePx = resolveVirtualCursorFollowTargetDistancePx(followMaxDistancePx);
  return clampBuddyPosition(
    {
      x: cursorCenter.x + unitX * followTargetDistancePx - DEFAULT_BUDDY_SIZE.width / 2,
      y: cursorCenter.y + unitY * followTargetDistancePx - DEFAULT_BUDDY_SIZE.height / 2,
    },
    viewport,
    DEFAULT_BUDDY_SIZE,
    DEFAULT_BUDDY_MARGIN,
  );
}

import React from 'react';
import { Cog6ToothIcon } from '@heroicons/react/24/outline';

interface GearIconProps {
  className?: string;
  color?: string;
  size?: number;
}

/** Шестерёнка для декора фона (как в макете) */
export function GearIcon({ className = '', color = '#B0BDD9', size = 80 }: GearIconProps) {
  return (
    <Cog6ToothIcon
      className={className}
      style={{ width: size, height: size, color }}
      aria-hidden
    />
  );
}

/** Упрощённый вариант — та же иконка, можно задать другой цвет/размер */
export function SimpleGearIcon({ className = '', color = '#FCC67F', size = 50 }: GearIconProps) {
  return (
    <Cog6ToothIcon
      className={className}
      style={{ width: size, height: size, color }}
      aria-hidden
    />
  );
}

import React from 'react';
import { GearIcon, SimpleGearIcon } from './GearIcon';

export const BackgroundShapes: React.FC = () => (
  <div className="absolute inset-0 pointer-events-none overflow-hidden" aria-hidden>
    <GearIcon
      className="absolute top-[12%] left-[8%] opacity-40"
      color="#B0BDD9"
      size={100}
    />
    <SimpleGearIcon
      className="absolute top-[25%] right-[12%] opacity-30"
      color="#B0BDD9"
      size={70}
    />
    <SimpleGearIcon
      className="absolute bottom-[35%] left-[15%] opacity-35"
      color="#FCC67F"
      size={60}
    />
    <SimpleGearIcon
      className="absolute bottom-[25%] right-[10%] opacity-25"
      color="#B0BDD9"
      size={50}
    />
    <SimpleGearIcon
      className="absolute top-[50%] right-[25%] opacity-30"
      color="#FCC67F"
      size={50}
    />
  </div>
);

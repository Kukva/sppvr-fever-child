import React from 'react';

interface DoctorProps {
  className?: string;
  scale?: number;
}

/** Декоративные SVG-иллюстрации из макета главного экрана */
export function DoctorLeft({ className, scale = 1 }: DoctorProps) {
  return (
    <div className={className} style={{ transform: `scale(${scale})`, transformOrigin: 'center' }}>
      <svg width="200" height="300" viewBox="0 0 200 300" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="40" y="200" width="30" height="100" fill="#B0BDD9" />
        <rect x="40" y="280" width="30" height="20" fill="black" rx="5" />
        <rect x="90" y="200" width="30" height="100" fill="#B0BDD9" />
        <rect x="90" y="280" width="30" height="20" fill="black" rx="5" />
        <rect x="35" y="100" width="90" height="110" fill="#2A9FFF" rx="5" />
        <rect x="10" y="110" width="30" height="80" fill="#B0BDD9" rx="5" />
        <circle cx="25" cy="195" r="8" fill="white" />
        <rect x="120" y="110" width="30" height="80" fill="#B0BDD9" rx="5" />
        <circle cx="135" cy="195" r="8" fill="white" />
        <rect x="50" y="50" width="60" height="60" fill="#FCC67F" rx="10" />
        <rect x="50" y="45" width="60" height="20" fill="black" rx="10" />
        <rect x="85" y="140" width="25" height="35" fill="#B0BDD9" rx="3" />
        <rect x="88" y="145" width="19" height="8" fill="white" rx="2" />
        <circle cx="80" cy="130" r="6" fill="white" />
        <circle cx="160" cy="80" r="6" fill="#A5F898" />
        <circle cx="170" cy="60" r="5" fill="#A5F898" />
      </svg>
    </div>
  );
}

export function DoctorRight({ className, scale = 1 }: DoctorProps) {
  return (
    <div className={className} style={{ transform: `scale(${scale})`, transformOrigin: 'center' }}>
      <svg width="200" height="300" viewBox="0 0 200 300" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="50" y="200" width="30" height="100" fill="#2A9FFF" />
        <rect x="50" y="280" width="30" height="20" fill="black" rx="5" />
        <rect x="100" y="200" width="30" height="100" fill="#2A9FFF" />
        <rect x="100" y="280" width="30" height="20" fill="black" rx="5" />
        <path
          d="M 40 100 L 40 200 L 65 200 L 65 210 L 115 210 L 115 200 L 140 200 L 140 100 L 40 100 Z"
          fill="#2A9FFF"
        />
        <rect x="15" y="110" width="30" height="90" fill="#B0BDD9" rx="5" />
        <circle cx="30" cy="205" r="8" fill="white" />
        <rect x="135" y="110" width="30" height="70" fill="#B0BDD9" rx="5" />
        <rect x="140" y="180" width="40" height="50" fill="#FCC67F" rx="5" />
        <rect x="145" y="185" width="30" height="10" fill="black" rx="2" />
        <circle cx="160" cy="210" r="4" fill="#BFFF00" />
        <rect x="60" y="40" width="60" height="70" fill="#FCC67F" rx="10" />
        <ellipse cx="90" cy="45" rx="35" ry="15" fill="black" />
        <circle cx="110" cy="50" r="12" fill="black" />
        <rect x="75" y="120" width="30" height="8" fill="white" rx="4" />
        <circle cx="25" cy="70" r="6" fill="#B0BDD9" />
      </svg>
    </div>
  );
}

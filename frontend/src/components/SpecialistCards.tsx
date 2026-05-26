import React, { useState } from 'react';
import { 
  StarIcon,
  MapPinIcon,
  PhoneIcon,
  EnvelopeIcon,
  ClockIcon,
  CheckCircleIcon
} from '@heroicons/react/24/outline';
import { StarIcon as StarIconSolid } from '@heroicons/react/24/solid';
import type { Specialist } from '../types';

interface SpecialistCardsProps {
  specialists: Specialist[];
  isLoading?: boolean;
  onContactSpecialist?: (specialist: Specialist) => void;
}

export const SpecialistCards: React.FC<SpecialistCardsProps> = ({
  specialists,
  isLoading = false,
  onContactSpecialist,
}) => {
  const [selectedSpecialty, setSelectedSpecialty] = useState<string>('all');
  
  const specialties = Array.from(new Set(specialists.map(s => s.specialty)));
  
  const filteredSpecialists = selectedSpecialty === 'all' 
    ? specialists 
    : specialists.filter(s => s.specialty === selectedSpecialty);

  const getAvailabilityColor = (availability: string) => {
    switch (availability) {
      case 'available':
        return 'text-green-600 bg-green-100';
      case 'busy':
        return 'text-yellow-600 bg-yellow-100';
      case 'offline':
        return 'text-gray-600 bg-gray-100';
      default:
        return 'text-gray-600 bg-gray-100';
    }
  };

  const getAvailabilityLabel = (availability: string) => {
    switch (availability) {
      case 'available':
        return 'Доступен';
      case 'busy':
        return 'Занят';
      case 'offline':
        return 'Недоступен';
      default:
        return 'Неизвестно';
    }
  };

  const renderStars = (rating: number) => {
    const stars = [];
    const fullStars = Math.floor(rating);
    const hasHalfStar = rating % 1 !== 0;

    for (let i = 0; i < fullStars; i++) {
      stars.push(
        <StarIconSolid key={i} className="w-4 h-4 text-yellow-400" />
      );
    }

    if (hasHalfStar) {
      stars.push(
        <StarIconSolid key="half" className="w-4 h-4 text-yellow-400 opacity-50" />
      );
    }

    const emptyStars = 5 - Math.ceil(rating);
    for (let i = 0; i < emptyStars; i++) {
      stars.push(
        <StarIcon key={`empty-${i}`} className="w-4 h-4 text-gray-300" />
      );
    }

    return stars;
  };

  const handleContact = (specialist: Specialist) => {
    if (onContactSpecialist) {
      onContactSpecialist(specialist);
    }
  };

  if (isLoading) {
    return (
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Рекомендуемые специалисты</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="specialist-card animate-pulse">
              <div className="flex items-center space-x-3 mb-3">
                <div className="w-12 h-12 bg-gray-200 rounded-full"></div>
                <div className="flex-1">
                  <div className="h-4 bg-gray-200 rounded mb-2"></div>
                  <div className="h-3 bg-gray-200 rounded w-3/4"></div>
                </div>
              </div>
              <div className="space-y-2">
                <div className="h-3 bg-gray-200 rounded"></div>
                <div className="h-3 bg-gray-200 rounded w-5/6"></div>
                <div className="h-3 bg-gray-200 rounded w-4/6"></div>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (specialists.length === 0) {
    return (
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Рекомендуемые специалисты</h3>
        </div>
        <div className="text-center py-8 text-gray-500">
          <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <CheckCircleIcon className="w-8 h-8 text-gray-400" />
          </div>
          <p>Специалисты не найдены</p>
          <p className="text-sm mt-2">
            Попробуйте изменить параметры поиска или обратитесь к общим рекомендациям
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="card-header">
        <h3 className="card-title">Рекомендуемые специалисты ({specialists.length})</h3>
        <p className="card-description">
          Специалисты для маршрутизации и дообследования пациента
        </p>
      </div>

      {/* Filter by Specialty */}
      {specialties.length > 1 && (
        <div className="mb-6">
          <label className="form-label">Фильтр по специальности:</label>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setSelectedSpecialty('all')}
              className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
                selectedSpecialty === 'all'
                  ? 'bg-medical-blue text-white'
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
            >
              Все ({specialists.length})
            </button>
            {specialties.map((specialty) => (
              <button
                key={specialty}
                onClick={() => setSelectedSpecialty(specialty)}
                className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
                  selectedSpecialty === specialty
                    ? 'bg-medical-blue text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                {specialty} ({specialists.filter(s => s.specialty === specialty).length})
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Specialists Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredSpecialists.map((specialist) => (
          <div key={specialist.id} className="specialist-card">
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center space-x-3">
                <div className="specialist-avatar">
                  {specialist.name.split(' ').map(n => n[0]).join('').toUpperCase()}
                </div>
                <div>
                  <h4 className="font-semibold text-gray-900">{specialist.name}</h4>
                  <p className="text-sm text-gray-600">{specialist.specialty}</p>
                </div>
              </div>
              
              <span className={`px-2 py-1 rounded-full text-xs font-medium ${getAvailabilityColor(
                specialist.availability
              )}`}>
                {getAvailabilityLabel(specialist.availability)}
              </span>
            </div>

            {/* Rating */}
            <div className="flex items-center space-x-1 mb-2">
              <div className="flex items-center">
                {renderStars(specialist.rating)}
              </div>
              <span className="text-sm text-gray-600 ml-1">
                {specialist.rating.toFixed(1)}
              </span>
            </div>

            {/* Experience */}
            <div className="text-sm text-gray-600 mb-3">
              Опыт: {specialist.experience}
            </div>

            {/* Location */}
            <div className="flex items-center text-sm text-gray-600 mb-2">
              <MapPinIcon className="w-4 h-4 mr-1 text-gray-400" />
              {specialist.location}
            </div>

            {/* Contact Info */}
            <div className="space-y-1 mb-4">
              {specialist.contactInfo.phone && (
                <div className="flex items-center text-sm text-gray-600">
                  <PhoneIcon className="w-4 h-4 mr-1 text-gray-400" />
                  {specialist.contactInfo.phone}
                </div>
              )}
              {specialist.contactInfo.email && (
                <div className="flex items-center text-sm text-gray-600">
                  <EnvelopeIcon className="w-4 h-4 mr-1 text-gray-400" />
                  {specialist.contactInfo.email}
                </div>
              )}
              {specialist.contactInfo.address && (
                <div className="flex items-center text-sm text-gray-600">
                  <MapPinIcon className="w-4 h-4 mr-1 text-gray-400" />
                  {specialist.contactInfo.address}
                </div>
              )}
            </div>

            {/* Contact Button */}
            <button
              onClick={() => handleContact(specialist)}
              className={`w-full btn ${
                specialist.availability === 'available'
                  ? 'btn-primary'
                  : 'btn-secondary'
              }`}
              disabled={specialist.availability === 'offline'}
            >
              {specialist.availability === 'available' ? (
                'Связаться'
              ) : specialist.availability === 'busy' ? (
                'Занят'
              ) : (
                'Недоступен'
              )}
            </button>
          </div>
        ))}
      </div>

      {/* No Results for Filter */}
      {filteredSpecialists.length === 0 && selectedSpecialty !== 'all' && (
        <div className="text-center py-8 text-gray-500">
          <p>Специалисты по специальности "{selectedSpecialty}" не найдены</p>
          <button
            onClick={() => setSelectedSpecialty('all')}
            className="mt-2 text-medical-blue hover:underline text-sm"
          >
            Показать всех специалистов
          </button>
        </div>
      )}

      {/* Info Section */}
      <div className="mt-6 p-4 bg-blue-50 rounded-lg border border-blue-200">
        <div className="flex items-start space-x-2">
          <ClockIcon className="w-5 h-5 text-blue-600 mt-0.5" />
          <div>
            <h4 className="font-medium text-blue-900 mb-1">Информация о записи</h4>
            <p className="text-sm text-blue-800">
              Рекомендуется предварительно позвонить специалисту для уточнения времени приема 
              и наличия свободных слотов. Некоторые специалисты могут требовать направление от врача.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SpecialistCards;
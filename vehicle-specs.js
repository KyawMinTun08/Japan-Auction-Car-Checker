/*
 * JACC vehicle specification reference catalog.
 *
 * This file contains public, model-level reference data only. It does not
 * decode an exact production year, grade, mileage, accident history, or
 * auction condition from a chassis number. Those values continue to come
 * from the Sheet record or a verified provider response.
 */
(function (window) {
  'use strict';

  window.JACC_VEHICLE_SPECIFICATIONS = [
    {
      key: 'toyota-alphard-ah30-25-gasoline',
      prefixes: ['AGH30', 'AGH30W', 'AGH35', 'AGH35W'],
      make: 'Toyota',
      model: 'Alphard',
      generation: 'AH30 / 30 Series',
      chassis: 'AGH30W / AGH35W',
      production: '2015–2023',
      bodyType: 'Minivan',
      engine: '2AR-FE',
      engineSize: '2,493 cc (2.5L Petrol)',
      engineType: 'Inline-4, Dual VVT-i',
      drive: 'AGH30 = 2WD (FF) · AGH35 = 4WD',
      gearbox: 'Super CVT-i',
      power: '182 PS (134 kW) / 6,000 rpm',
      torque: '235 Nm / 4,100 rpm',
      fuel: 'Regular Petrol (RON 91)',
      fuelTank: '75L (2WD) / 65L (4WD)',
      seats: '7 / 8 seats (grade dependent)',
      description: 'AGH30 သည် 2.5L Petrol 2WD (FF) ဖြစ်ပြီး AGH35 သည် 2.5L Petrol 4WD ဖြစ်ပါတယ်။ Hybrid မော်ဒယ်ကိုတော့ AYH30W prefix ဖြင့် သီးခြားစစ်ပါ။',
      checks: 'CVT fluid နှင့် maintenance history၊ water pump/cooling system၊ engine oil leak၊ power sliding doors နှင့် grade/package ကို စစ်ဆေးပါ။',
      references: [
        { label: 'Toyota-Club technical data', url: 'https://toyota-club.net/files/techdata/ttx/alphard_30.htm' },
        { label: 'Goo-net 2.5S catalogue', url: 'https://www.goo-net-exchange.com/catalog/TOYOTA__ALPHARD/10127796/' }
      ]
    },
    {
      key: 'toyota-alphard-ah30-35-gasoline',
      prefixes: ['GGH30', 'GGH30W', 'GGH35', 'GGH35W'],
      make: 'Toyota',
      model: 'Alphard / Vellfire 3.5',
      generation: 'AH30 / 30 Series',
      chassis: 'GGH30W / GGH35W',
      production: '2015–2023',
      bodyType: 'Minivan',
      engine: '2GR-FE / 2GR-FKS',
      engineSize: '3,456 cc (3.5L Petrol)',
      engineType: 'V6 Petrol',
      drive: 'GGH30 = 2WD (FF) · GGH35 = 4WD',
      gearbox: '6AT or 8AT (year dependent)',
      fuel: 'Premium Petrol',
      seats: '7 / 8 seats (grade dependent)',
      description: '3.5L Alphard/Vellfire grade ဖြစ်သောကြောင့် engine code၊ facelift year နှင့် gearbox ကို chassis/grade အလိုက် ထပ်စစ်ပါ။',
      checks: 'Engine oil/cooling system၊ 6AT/8AT service history နှင့် trim/package ကို စစ်ဆေးပါ။',
      references: [
        { label: 'Toyota-Club technical data', url: 'https://toyota-club.net/files/techdata/ttx/alphard_30.htm' }
      ]
    },
    {
      key: 'toyota-alphard-ah30-hybrid',
      prefixes: ['AYH30', 'AYH30W'],
      make: 'Toyota',
      model: 'Alphard Hybrid',
      generation: 'AH30 / 30 Series',
      chassis: 'AYH30W',
      production: '2015–2023',
      bodyType: 'Hybrid Minivan',
      engine: '2AR-FXE + Hybrid Motor',
      engineSize: '2,493 cc (2.5L Hybrid)',
      engineType: 'Inline-4 Hybrid',
      drive: 'E-Four (Hybrid 4WD)',
      gearbox: 'Hybrid / e-CVT',
      fuel: 'Regular Petrol',
      fuelTank: '65L',
      seats: '7 / 8 seats (grade dependent)',
      description: 'AYH30W သည် 2.5L Hybrid မော်ဒယ်ဖြစ်ပြီး battery၊ inverter နှင့် hybrid system health ကို သီးခြားစစ်ဆေးရန်လိုပါတယ်။',
      checks: 'Hybrid battery/inverter၊ cooling system၊ hybrid warning history နှင့် service record ကို စစ်ဆေးပါ။',
      references: [
        { label: 'Toyota-Club technical data', url: 'https://toyota-club.net/files/techdata/ttx/alphard_30.htm' }
      ]
    }
  ];
})(window);

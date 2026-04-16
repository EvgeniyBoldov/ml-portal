# Руководство сетевого инженера компании "Дубалайн"

## 1. Введение и общие положения

### 1.1. Назначение документа
Настоящее руководство определяет стандарты работы, процедуры и лучшие практики для сетевых инженеров компании "Дубалайн". Документ является обязательным для исполнения всеми сотрудниками, выполняющими работы по настройке, поддержке и развитию сетевой инфраструктуры.

### 1.2. Область применения
Руководство распространяется на:
- Проектирование и внедрение сетевых решений
- Администрирование активного сетевого оборудования
- Траублшутинг и устранение инцидентов
- Оптимизация и модернизация сети
- Взаимодействие с другими ИТ-службами

### 1.3. Организационная структура

#### 1.3.1. Отдел сетевой инфраструктуры
```
Руководитель отдела сетевой инфраструктуры
├── Ведущий сетевой инженер (Core Network)
├── Сетевые инженеры (Data Center)
├── Сетевые инженеры (Campus Network)
├── Инженеры по эксплуатации (NOC)
└── Инженеры по безопасности (Network Security)
```

#### 1.3.2. Зоны ответственности
- **Core Network**: Магистральные маршрутизаторы, core коммутаторы, MPLS
- **Data Center**: Коммутаторы серверных стоек, SAN, storage networking
- **Campus Network**: Access коммутаторы, Wi-Fi, IP-телефония
- **NOC**: Мониторинг, первая линия поддержки, документация
- **Network Security**: Файрволы, IDS/IPS, VPN, NAC

### 1.4. Термины и определения

| Термин | Определение |
|--------|-------------|
| **Core Network** | Магистральная сеть, соединяющая основные узлы инфраструктуры |
| **Distribution Layer** | Уровень распределения, агрегация access сетей |
| **Access Layer** | Уровень доступа, конечные устройства пользователей |
| **VLAN** | Виртуальная локальная сеть, логическое разделение сети |
| **STP** | Spanning Tree Protocol, предотвращение петлевых маршрутов |
| **OSPF** | Open Shortest Path First, протокол динамической маршрутизации |
| **BGP** | Border Gateway Protocol, протокол междоменной маршрутизации |
| **QoS** | Quality of Service, качество обслуживания трафика |
| **NAC** | Network Access Control, контроль доступа в сеть |
| **SD-WAN** | Software-Defined Wide Area Network |
| **Zero Trust** | Архитектура нулевого доверия |

## 2. Стандарты сетевой инфраструктуры

### 2.1. Иерархическая модель сети

#### 2.1.1. Трехуровневая иерархия
```
Internet
    |
[Core Layer] - Магистральные маршрутизаторы (Cisco ASR 1000)
    |
[Distribution Layer] - Агрегационные коммутаторы (Cisco Catalyst 9500)
    |
[Access Layer] - Коммутаторы доступа (Cisco Catalyst 9300/9200)
    |
[End Devices] - Серверы, рабочие станции, IP-телефоны
```

#### 2.1.2. Принципы проектирования
- **Иерархичность**: Четкое разделение на уровни
- **Модульность**: Логическое разделение на функциональные блоки
- **Резервирование**: Отсутствие единой точки отказа
- **Масштабируемость**: Возможность расширения без редизайна
- **Безопасность**: Многоуровневая защита

### 2.2. Стандарты именования

#### 2.2.1. Именование устройств
Формат: `[ТИП]-[ЛОКАЦИЯ]-[НОМЕР]-[ФУНКЦИЯ]`

Примеры:
- `CORE-DC01-01-Main` - Core коммутатор в ЦОД1
- `DIST-OF01-01-Agg` - Distribution коммутатор в офисе 1
- `ACC-DC01-01-Srv01` - Access коммутатор серверной стойки 01
- `FW-EDGE-01-Ext` - Пограничный файрвол

#### 2.2.2. Именование интерфейсов
- `TenGigabitEthernet1/1/1` - Uplink к core
- `GigabitEthernet1/0/1` - Access порт
- `Port-channel1` - LAG интерфейс
- `Vlan10` - SVI интерфейс

#### 2.2.3. Именование VLAN
Формат: `[ТИП]-[НАЗНАЧЕНИЕ]-[НОМЕР]`

Примеры:
- `MGMT-MGMT-10` - Management VLAN
- `SRV-DB-20` - Серверы баз данных
- `USR-IT-30` - Пользователи IT отдела
- `GUEST-WIFI-40` - Гостевая Wi-Fi сеть

### 2.3. Стандарты IP-адресации

#### 2.3.1. Схема адресации
```
10.0.0.0/8 - Внутренняя сеть
├── 10.1.0.0/16 - Management
├── 10.2.0.0/16 - Servers
├── 10.3.0.0/16 - Users
├── 10.4.0.0/16 - Voice
├── 10.5.0.0/16 - Storage
├── 10.6.0.0/16 - Security
├── 10.7.0.0/16 - Guest
├── 10.8.0.0/16 - DMZ
├── 10.9.0.0/16 - Backup
└── 10.254.0.0/16 - Infrastructure
```

#### 2.3.2. Резервирование адресов
- `.1` - Gateway/Router
- `.2-.10` - Infrastructure devices
- `.11-.50` - Servers
- `.51-.200` - Users/DHCP
- `.201-.254` - Static assignments

### 2.4. Стандарты безопасности

#### 2.4.1. Политики доступа
- Минимальные привилегии (Principle of Least Privilege)
- Ролевая модель доступа (RBAC)
- Многофакторная аутентификация
- Регулярная ротация паролей

#### 2.4.2. Сегментация сети
- Изоляция критичных систем
- DMZ для публичных сервисов
- Guest сеть с ограниченным доступом
- IoT сеть с контролируемым доступом

#### 2.4.3. Мониторинг безопасности
- SIEM система для логов
- IDS/IPS для обнаружения атак
- NetFlow для анализа трафика
- Регулярные сканирования уязвимостей

## 3. Процедуры эксплуатации

### 3.1. Ежедневные процедуры

#### 3.1.1. Утренняя проверка (09:00)
```
1. Проверка доступности core устройств (ping, SNMP)
2. Анализ загрузки процессора и памяти
3. Проверка статуса интерфейсов
4. Просмотр системных логов
5. Проверка доступности ключевых сервисов
6. Анализ сетевых инцидентов за ночь
```

#### 3.1.2. Вечерняя проверка (18:00)
```
1. Проверка бэкапов конфигураций
2. Анализ дневных метрик производительности
3. Проверка открытых тикетов
4. Подготовка отчета о состоянии сети
5. Планирование работ на следующее время
```

### 3.2. Еженедельные процедуры

#### 3.2.1. Обслуживание (Пятница 16:00-18:00)
```
1. Обновление ПО на устройствах (при необходимости)
2. Проверка и очистка логов
3. Анализ утилизации каналов
4. Тестирование отказоустойчивости
5. Обновление документации
6. Планирование работ на следующую неделю
```

#### 3.2.2. Анализ производительности
```
1. Анализ топологии сети
2. Оптимизация маршрутизации
3. Проверка баланса нагрузки
4. Анализ паттернов трафика
5. Выявление узких мест
```

### 3.3. Ежемесячные процедуры

#### 3.3.1. Капитальное обслуживание
```
1. Полная проверка всех устройств
2. Тестирование систем резервирования
3. Аудит безопасности
4. Обновление антивирусных баз
5. Проверка систем мониторинга
6. Обучение персонала
```

#### 3.3.2. Отчетность
```
1. Отчет о доступности сервисов
2. Анализ инцидентов
3. Отчет о производительности
4. План развития сети
5. Бюджетные предложения
```

## 4. Процедуры настройки оборудования

### 4.1. Базовая настройка Cisco IOS

#### 4.1.1. Начальная конфигурация
```cisco
! Базовые настройки
hostname SWITCH-LOCATION-01
!
! Настройка времени и NTP
clock timezone MSK +3
ntp server 10.254.1.1
!
! Настройка домена и DNS
ip domain-name dubaline.local
ip name-server 10.254.1.2 10.254.1.3
!
! Создание пользователя
username admin privilege 15 secret $9$encrypted_password
!
! Настройка enable secret
enable secret $9$encrypted_enable_secret
!
! Настройка консоли
line con 0
 exec-timeout 5 0
 logging synchronous
!
! Настройка VTY
line vty 0 4
 exec-timeout 10 0
 login local
 transport input ssh
!
! Отключение telnet
no ip telnet server
!
! Настройка SNMP
snmp-server community Dubalaine_RO RO
snmp-server community Dubalaine_RW RW
snmp-server location "Data Center 1, Rack 01"
snmp-server contact "Network Team"
!
! Настройка syslog
logging 10.254.1.10
logging trap informational
!
! Сохранение конфигурации
end
write memory
```

#### 4.1.2. Настройка VLAN
```cisco
! Создание VLAN
vlan 10
 name MGMT-MGMT-10
!
vlan 20
 name SRV-DB-20
!
vlan 30
 name USR-IT-30
!
vlan 40
 name GUEST-WIFI-40
!
! Настройка SVI интерфейсов
interface Vlan10
 description Management Network
 ip address 10.1.10.1 255.255.255.0
 no shutdown
!
interface Vlan20
 description Database Servers
 ip address 10.2.20.1 255.255.255.0
 no shutdown
!
interface Vlan30
 description IT Users
 ip address 10.3.30.1 255.255.255.0
 no shutdown
!
interface Vlan40
 description Guest WiFi
 ip address 10.7.40.1 255.255.255.0
 no shutdown
!
! Настройка default gateway
ip default-gateway 10.1.10.254
```

#### 4.1.3. Настройка интерфейсов
```cisco
! Uplink интерфейс
interface TenGigabitEthernet1/1/1
 description Uplink to CORE-DC01-01
 switchport mode trunk
 switchport trunk allowed vlan 10,20,30
 spanning-tree portfast trunk
!
! Access порт для сервера
interface GigabitEthernet1/0/1
 description Server-DB-01
 switchport mode access
 switchport access vlan 20
 switchport port-security
 switchport port-security maximum 2
 switchport port-security mac-address sticky
 spanning-tree portfast
!
! Access порт для пользователя
interface GigabitEthernet1/0/24
 description User-Workstation
 switchport mode access
 switchport access vlan 30
 switchport port-security
 switchport port-security maximum 1
 switchport port-security violation shutdown
 spanning-tree portfast
!
! Порт для IP телефона
interface GigabitEthernet1/0/48
 description IP-Phone-User
 switchport mode access
 switchport access vlan 30
 switchport voice vlan 40
 spanning-tree portfast
!
! LAG интерфейс
interface Port-channel1
 description LAG to DIST-OF01-01
 switchport mode trunk
!
interface TenGigabitEthernet1/1/2
 channel-group 1 mode active
!
interface TenGigabitEthernet1/1/3
 channel-group 1 mode active
```

### 4.2. Настройка маршрутизации

#### 4.2.1. OSPF конфигурация
```cisco
! Включение OSPF
router ospf 1
 router-id 10.1.10.1
 log-adjacency-changes
!
! Объявление сетей
 network 10.1.10.0 0.0.0.255 area 0
 network 10.2.20.0 0.0.0.255 area 0
 network 10.3.30.0 0.0.0.255 area 0
!
! Настройка пассивных интерфейсов
 passive-interface default
 no passive-interface TenGigabitEthernet1/1/1
!
! Настройка стоимостей
 auto-cost reference-bandwidth 10000
!
! Фильтрация маршрутов
 distribute-list prefix OSPF_FILTER_IN in
!
! Настройка аутентификации
 area 0 authentication message-digest
!
interface Vlan10
 ip ospf authentication message-digest
 ip ospf message-digest-key 1 md5 Dubalaine_OSPF_Key
!
interface Vlan20
 ip ospf authentication message-digest
 ip ospf message-digest-key 1 md5 Dubalaine_OSPF_Key
!
! Prefix-list для фильтрации
ip prefix-list OSPF_FILTER_IN seq 5 permit 10.0.0.0/8 le 24
ip prefix-list OSPF_FILTER_IN seq 10 deny 0.0.0.0/0 le 32
```

#### 4.2.2. BGP конфигурация
```cisco
! Включение BGP
router bgp 65001
 bgp router-id 10.254.1.1
 bgp log-neighbor-changes
!
! Объявление сетей
 network 10.0.0.0 mask 255.0.0.0
!
! Настройка соседа
 neighbor 192.168.1.1 remote-as 65530
 neighbor 192.168.1.1 description ISP-Primary
 neighbor 192.168.1.1 password 7 encrypted_password
 neighbor 192.168.1.1 route-map ISP_IN in
 neighbor 192.168.1.1 route-map ISP_OUT out
!
! Настройка фильтрации
ip as-path access-list 1 deny ^$
ip as-path access-list 1 permit .*
!
! Route-maps
route-map ISP_IN permit 10
 set local-preference 100
!
route-map ISP_OUT permit 10
 set as-path prepend 65001 65001
!
! Настройка prefix-list
ip prefix-list ANNOUNCE seq 5 permit 10.0.0.0/8
```

### 4.3. Настройка безопасности

#### 4.3.1. Access Control Lists
```cisco
! Стандартный ACL для управления
ip access-list standard MGMT_ACCESS
 permit 10.1.10.0 0.0.0.255
 permit 10.254.0.0 0.0.0.255
 deny any
!
! Расширенный ACL для серверов
ip access-list extended SRV_SECURITY
 permit tcp any any established
 permit tcp any host 10.2.20.10 eq 22
 permit tcp any host 10.2.20.10 eq 443
 permit udp any host 10.2.20.20 eq domain
 permit udp any host 10.2.20.20 eq ntp
 deny ip any any
!
! Применение ACL
line vty 0 4
 access-class MGMT_ACCESS in
!
interface Vlan20
 ip access-group SRV_SECURITY in
```

#### 4.3.2. Port Security
```cisco
! Настройка port security
interface range GigabitEthernet1/0/1-48
 switchport port-security
 switchport port-security maximum 2
 switchport port-security mac-address sticky
 switchport port-security violation shutdown
 switchport port-security aging time 5
 switchport port-security aging type inactivity
!
! Настройка recovery
errdisable recovery cause psecure-violation
errdisable recovery interval 30
```

#### 4.3.3. DHCP Snooping
```cisco
! Включение DHCP snooping
ip dhcp snooping
ip dhcp snooping vlan 30
!
! Настройка trusted портов
interface TenGigabitEthernet1/1/1
 ip dhcp snooping trust
!
interface TenGigabitEthernet1/1/2
 ip dhcp snooping trust
!
! Ограничение rate
interface range GigabitEthernet1/0/1-48
 ip dhcp snooping limit rate 100
```

### 4.4. Настройка QoS

#### 4.4.1. Классификация трафика
```cisco
! Создание классов
class-map match-any VOICE_TRAFFIC
 match dscp ef
 match cos 5
!
class-map match-any VIDEO_TRAFFIC
 match dscp af41
 match cos 4
!
class-map match-any CRITICAL_DATA
 match dscp af31
 match cos 3
!
class-map match-any BEST_EFFORT
 match any
```

#### 4.4.2. Политики QoS
```cisco
! Создание политик
policy-map QOS_POLICY
 class VOICE_TRAFFIC
  priority percent 30
 class VIDEO_TRAFFIC
  bandwidth percent 20
 class CRITICAL_DATA
  bandwidth percent 30
 class BEST_EFFORT
  bandwidth percent 20
!
! Применение политик
interface range GigabitEthernet1/0/1-48
 service-policy output QOS_POLICY
!
interface TenGigabitEthernet1/1/1
 service-policy input QOS_POLICY
 service-policy output QOS_POLICY
```

## 5. Процедуры траублшутинга

### 5.1. Методология диагностики

#### 5.1.1. OSI модель подхода
```
7. Application Layer - Проверка приложений и сервисов
6. Presentation Layer - Формат данных, шифрование
5. Session Layer - Сессии, аутентификация
4. Transport Layer - TCP/UDP, порты
3. Network Layer - IP адресация, маршрутизация
2. Data Link Layer - MAC адреса, VLAN, STP
1. Physical Layer - Кабели, порты, питание
```

#### 5.1.2. Порядок диагностики
1. **Сбор информации**: Что не работает? Когда началось? Что изменилось?
2. **Определение области**: Локальная проблема или глобальная?
3. **Проверка физического уровня**: Кабели, порты, питание
4. **Проверка L2 уровня**: VLAN, MAC адреса, STP
5. **Проверка L3 уровня**: IP адресация, маршрутизация
6. **Проверка L4+ уровней**: Порты, приложения, сервисы
7. **Анализ логов**: Системные логи, debug команды
8. **Тестирование**: Ping, traceroute, telnet, ssh

### 5.2. Диагностические команды

#### 5.2.1. Базовая диагностика
```cisco
! Проверка доступности
ping 10.1.10.1
ping 8.8.8.8
traceroute 8.8.8.8
!
! Проверка интерфейсов
show ip interface brief
show interfaces status
show interfaces counters
!
! Проверка ARP таблицы
show arp
show ip arp
!
! Проверка MAC таблицы
show mac address-table
show mac address-table dynamic
```

#### 5.2.2. VLAN и STP диагностика
```cisco
! Проверка VLAN
show vlan brief
show vlan id 10
show interfaces trunk
!
! Проверка STP
show spanning-tree
show spanning-tree vlan 10
show spanning-tree detail
show spanning-tree blockedports
```

#### 5.2.3. Маршрутизация диагностика
```cisco
! Проверка таблицы маршрутизации
show ip route
show ip route 10.2.20.0
show ip route ospf
!
! Проверка OSPF
show ip ospf neighbor
show ip ospf database
show ip ospf interface
!
! Проверка BGP
show ip bgp summary
show ip bgp neighbors
show ip bgp routes
```

#### 5.2.4. Безопасность диагностика
```cisco
! Проверка ACL
show access-lists
show ip access-lists
show mac access-list
!
! Проверка port security
show port-security
show port-security interface
show port-security address
!
! Проверка DHCP snooping
show ip dhcp snooping
show ip dhcp snooping binding
```

### 5.3. Частые проблемы и решения

#### 5.3.1. Проблема: Нет связи с устройством
**Возможные причины:**
- Устройство выключено или проблема с питанием
- Проблема с кабелем или портом
- Неправильная IP конфигурация
- Проблема с VLAN

**Решение:**
1. Проверить питание и статус устройства
2. Проверить кабель и порт (`show interfaces status`)
3. Проверить IP конфигурацию (`show ip interface brief`)
4. Проверить VLAN (`show vlan brief`)

#### 5.3.2. Проблема: Медленная работа сети
**Возможные причины:**
- Высокая загрузка процессора/памяти
- Перегрузка каналов
- Ошибки на интерфейсах
- Проблемы с QoS

**Решение:**
1. Проверить загрузку (`show processes cpu`, `show memory`)
2. Проверить утилизацию интерфейсов (`show interfaces`)
3. Проверить ошибки (`show interfaces counters errors`)
4. Проверить QoS (`show policy-map interface`)

#### 5.3.3. Проблема: Проблемы с доступом в интернет
**Возможные причины:**
- Проблема с провайдером
- Проблема с NAT
- Проблема с маршрутизацией
- Проблема с файрволом

**Решение:**
1. Проверить доступность провайдера (`ping ISP_gateway`)
2. Проверить NAT (`show ip nat translations`)
3. Проверить маршрутизацию (`show ip route`)
4. Проверить файрвол (`show access-lists`)

#### 5.3.4. Проблема: Broadcast storm
**Возможные причины:**
- Петля в сети
- Неправильная конфигурация STP
- Проблема с сетевой картой

**Решение:**
1. Проверить STP (`show spanning-tree`)
2. Найти порт с высокой загрузкой (`show interfaces`)
3. Отключить подозрительный порт
4. Анализировать топологию сети

## 6. Процедуры мониторинга

### 6.1. Системы мониторинга

#### 6.1.1. Zabbix мониторинг
- **Доступность**: ICMP ping, SNMP check
- **Производительность**: CPU, Memory, Interface utilization
- **События**: Syslog, SNMP traps
- **Автоматическое обнаружение**: Network discovery

#### 6.1.2. NetFlow анализ
- **Трафик**: Top talkers, protocols, applications
- **Безопасность**: DDoS detection, anomaly detection
- **Планирование**: Capacity planning, trend analysis

#### 6.1.3. SIEM система
- **Безопасность**: Security events, IDS/IPS alerts
- **Комплаенс**: Audit logs, compliance reporting
- **Инциденты**: Incident correlation, alerting

### 6.2. Ключевые метрики

#### 6.2.1. Доступность
- Uptime устройств (>99.9%)
- Доступность сервисов (>99.5%)
- Время восстановления (<4 часа)

#### 6.2.2. Производительность
- CPU Utilization (<70% среднее, <85% пиковое)
- Memory Utilization (<80% среднее, <90% пиковое)
- Interface Utilization (<70% среднее, <85% пиковое)

#### 6.2.3. Качество
- Packet Loss (<0.1%)
- Latency (<100ms для локальных, <500ms для удаленных)
- Jitter (<50ms для VoIP)

### 6.3. Алерты и уведомления

#### 6.3.1. Уровни критичности
- **Critical**: Массовый сбой, критичный сервис недоступен
- **Warning**: Деградация производительности, единичный сбой
- **Info**: Информационные сообщения, плановые работы

#### 6.3.2. Процедура оповещения
```
Critical: Немедленное уведомление (SMS, звонок)
Warning: Email уведомление (в течение 5 минут)
Info: Логирование без уведомления
```

## 7. Процедуры резервирования и восстановления

### 7.1. Резервное копирование

#### 7.1.1. Автоматическое бэкапирование
```bash
#!/bin/bash
# Сценарий бэкапа конфигураций Cisco
BACKUP_DIR="/backup/network/$(date +%Y%m%d)"
mkdir -p $BACKUP_DIR

# Список устройств
DEVICES="10.1.10.1 10.1.10.2 10.1.10.3"

for device in $DEVICES; do
    echo "Backing up $device"
    ssh admin@$device "show running-config" > $BACKUP_DIR/$device.cfg
done

# Архивирование
tar -czf $BACKUP_DIR.tar.gz $BACKUP_DIR
rm -rf $BACKUP_DIR
```

#### 7.1.2. Проверка бэкапов
- Ежедневная проверка успешности бэкапа
- Еженедельное тестирование восстановления
- Ежемесячная проверка полноты бэкапа

### 7.2. Восстановление после сбоя

#### 7.2.1. Процедура восстановления
1. **Оценка ситуации**: Определить масштаб проблемы
2. **Приоритизация**: Восстановление критичных сервисов в первую очередь
3. **Восстановление**: Поэтапное восстановление систем
4. **Тестирование**: Проверка работоспособности
5. **Документация**: Фиксация инцидента и уроков

#### 7.2.2. План аварийного восстановления
```
Phase 1: Core Network (0-2 часа)
- Восстановление core коммутаторов
- Восстановление магистральных каналов
- Восстановление интернет доступа

Phase 2: Distribution Layer (2-6 часов)
- Восстановление distribution коммутаторов
- Восстановление серверных сетей
- Восстановление пользовательских сетей

Phase 3: Access Layer (6-12 часов)
- Восстановление access коммутаторов
- Восстановление Wi-Fi сетей
- Восстановление периферийных устройств
```

## 8. Процедуры обучения и развития

### 8.1. Обучение персонала

#### 8.1.1. Обязательное обучение
- **Новички**: Базовый курс сетевых технологий (2 недели)
- **Опытные инженеры**: Продвинутый курс (1 неделя в квартал)
- **Все сотрудники**: Обучение безопасности (ежеквартально)

#### 8.1.2. Сертификация
- **Базовый уровень**: CCNA (обязательно для всех инженеров)
- **Продвинутый уровень**: CCNP (обязательно для ведущих инженеров)
- **Экспертный уровень**: CCIE (поощряется для специалистов)

### 8.2. Профессиональное развитие

#### 8.2.1. Технические навыки
- **Сетевые технологии**: OSPF, BGP, MPLS, SD-WAN
- **Безопасность**: Файрволы, IDS/IPS, VPN, NAC
- **Облачные технологии**: AWS Networking, Azure Networking
- **Автоматизация**: Python, Ansible, Netmiko

#### 8.2.2. Мягкие навыки
- **Коммуникация**: Взаимодействие с другими отделами
- **Проектный менеджмент**: Планирование и контроль проектов
- **Документация**: Ведение технической документации
- **Обучение**: Передача знаний младшим коллегам

## 9. Приложения

### 9.1. Чек-лист настройки нового устройства

```
□ Физическая установка и подключение
□ Начальная конфигурация (hostname, passwords)
□ Настройка времени и NTP
□ Настройка управления (SNMP, syslog)
□ Настройка VLAN и интерфейсов
□ Настройка маршрутизации
□ Настройка безопасности (ACL, port security)
□ Настройка мониторинга
□ Тестирование доступности
□ Обновление документации
□ Ввод в эксплуатацию
```

### 9.2. Шаблон отчета об инциденте

```
Инцидент #: INC-YYYY-MM-DD-XXX
Дата и время: DD.MM.YYYY HH:MM
Критичность: Critical/Warning/Info
Описание: [Краткое описание проблемы]
Влияние: [Затронутые системы и пользователи]
Причина: [Корневая причина инцидента]
Действия: [Предпринятые действия]
Результат: [Текущий статус]
Уроки: [Извлеченные уроки]
Предотвращение: [Меры по предотвращению]
```

### 9.3. Контактная информация

```
Экстренные ситуации:
- Руководитель отдела: +7 (XXX) XXX-XX-XX
- Ведущий инженер: +7 (XXX) XXX-XX-XX
- NOC дежурный: +7 (XXX) XXX-XX-XX

Поставщики услуг:
- ISP-1: +7 (XXX) XXX-XX-XX
- ISP-2: +7 (XXX) XXX-XX-XX
- Вендор Cisco: +7 (XXX) XXX-XX-XX
```

---

**Документ версия**: 1.0  
**Дата последнего обновления**: 20.02.2026  
**Ответственный**: Ведущий сетевой инженер  
**Периодичность пересмотра**: Полугодично

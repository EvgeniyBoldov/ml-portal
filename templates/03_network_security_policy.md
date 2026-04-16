# Политика безопасности сетевой инфраструктуры компании "Дубалайн"

## 1. Общие положения

### 1.1. Назначение документа
Настоящая политика определяет требования к безопасности сетевой инфраструктуры компании "Дубалайн", устанавливает стандарты защиты и процедуры реагирования на инциденты безопасности. Политика является обязательной для исполнения всеми сотрудниками и подрядчиками, имеющими доступ к сетевой инфраструктуре.

### 1.2. Область применения
Политика распространяется на:
- Все сетевые устройства (коммутаторы, маршрутизаторы, файрволы)
- Сетевые сервисы (DNS, DHCP, NTP, VPN)
- Системы управления и мониторинга
- Пользовательские устройства, подключаемые к корпоративной сети
- Облачные сервисы и внешние подключения

### 1.3. Цели политики
- **Конфиденциальность**: Защита корпоративных данных от несанкционированного доступа
- **Целостность**: Обеспечение точности и полноты данных и систем
- **Доступность**: Гарантированный доступ к ресурсам для авторизованных пользователей
- **Соответствие**: Соблюдение законодательных требований и стандартов

### 1.4. Термины и определения

| Термин | Определение |
|--------|-------------|
| **Zero Trust** | Архитектура безопасности, не доверяющая никому по умолчанию |
| **NAC** | Network Access Control, контроль доступа в сеть |
| **IDS/IPS** | Intrusion Detection/Prevention System |
| **SIEM** | Security Information and Event Management |
| **DLP** | Data Loss Prevention, предотвращение утечек данных |
| **MFA** | Multi-Factor Authentication, многофакторная аутентификация |
| **PKI** | Public Key Infrastructure, инфраструктура открытых ключей |
| **HSM** | Hardware Security Module, аппаратный модуль безопасности |
| **SOC** | Security Operations Center, центр мониторинга безопасности |

## 2. Архитектура безопасности

### 2.1. Модель Zero Trust

#### 2.1.1. Принципы Zero Trust
- **Never Trust, Always Verify**: Никогда не доверять, всегда проверять
- **Least Privilege Access**: Минимальные привилегии доступа
- **Micro-segmentation**: Микросегментация сети
- **Continuous Monitoring**: Непрерывный мониторинг и анализ

#### 2.1.2. Архитектурные слои
```
Internet
    |
[DMZ Layer] - Изолированная зона для публичных сервисов
    |
[Perimeter Security] - Пограничная безопасность (NGFW, IPS)
    |
[Core Security] - Безопасность магистральной сети
    |
[Segmentation] - Сегментация по типам данных и сервисов
    |
[Endpoint Security] - Безопасность конечных устройств
```

### 2.2. Сегментация сети

#### 2.2.1. Зоны безопасности
- **Critical Zone**: Критичная инфраструктура (AD, CA, HSM)
- **Restricted Zone**: Ограниченный доступ (базы данных, финансовые системы)
- **Production Zone**: Продуктивные системы (приложения, серверы)
- **Corporate Zone**: Корпоративные пользователи и ресурсы
- **Guest Zone**: Гостевая сеть с ограниченным доступом
- **IoT Zone**: Интернет вещей и периферийные устройства

#### 2.2.2. Правила сегментации
```cisco
! Пример ACL для сегментации
ip access-list extended CRITICAL_TO_RESTRICTED
 permit ip 10.1.1.0 0.0.0.255 10.1.2.0 0.0.0.255
 permit tcp 10.1.1.0 0.0.0.255 10.1.2.0 0.0.0.255 eq 1433
 permit tcp 10.1.1.0 0.0.0.255 10.1.2.0 0.0.0.255 eq 1521
 deny ip any any
!
ip access-list extended PRODUCTION_TO_CORPORATE
 permit tcp 10.1.3.0 0.0.0.255 10.1.4.0 0.0.0.255 eq 80
 permit tcp 10.1.3.0 0.0.0.255 10.1.4.0 0.0.0.255 eq 443
 permit tcp 10.1.3.0 0.0.0.255 10.1.4.0 0.0.0.255 eq 3389
 deny ip any any
```

### 2.3. Контроль доступа

#### 2.3.1. Network Access Control (NAC)
- **802.1X**: Аутентификация на портах коммутаторов
- **MAC Authentication Bypass (MAB)**: Для устройств без 802.1X
- **Web Authentication**: Для гостевых пользователей
- **Posture Assessment**: Проверка состояния устройств

#### 2.3.2. Ролевая модель доступа
| Роль | Уровень доступа | Разрешенные зоны | Ограничения |
|------|----------------|------------------|-------------|
| Administrator | Полный | Все зоны | Без ограничений |
| Network Engineer | Управление | Infrastructure | Production только по запросу |
| System Administrator | Серверы | Production, Restricted | Network только по запросу |
| Developer | Разработка | Dev, Test | Production запрещен |
| User | Пользователь | Corporate | Guest, IoT запрещены |
| Guest | Гость | Guest | Все остальные запрещены |

## 3. Защита периметра

### 3.1. Next Generation Firewall

#### 3.1.1. Требования к файрволу
- **Производительность**: Минимум 10 Gbps throughput
- **Функциональность**: NGFW с IPS, AV, URL filtering
- **Высокая доступность**: Active-Passive кластер
- **Модульность**: Возможность расширения функционала

#### 3.1.2. Правила файрвола
```bash
# Пример правил для Palo Alto Networks
# Политика для управления
rule "Allow Management from Admin Network" {
  source: 10.254.0.0/16
  destination: 10.1.0.0/16
  application: ssh, https, snmp
  action: allow
  log: yes
}

# Политика для интернет доступа
rule "Allow Internet Access for Corporate Users" {
  source: 10.1.4.0/16
  destination: any
  application: web-browsing, ssl, dns
  action: allow
  log: yes
}

# Политика для серверов
rule "Allow Specific Services from Internet" {
  source: any
  destination: 10.1.3.0/16
  application: web-browsing, ssl
  action: allow
  log: yes
}

# Политика по умолчанию
rule "Default Deny" {
  source: any
  destination: any
  application: any
  action: deny
  log: yes
}
```

### 3.2. Intrusion Detection/Prevention

#### 3.2.1. Стратегия развертывания
- **Network IDS**: Мониторинг трафика в зеркальных портах
- **Network IPS**: Встроенная в файрвол защита
- **Host IDS**: Агенты на критичных серверах
- **Cloud IDS**: Мониторинг облачных ресурсов

#### 3.2.2. Правила IPS
```xml
<!-- Пример правил для Snort -->
<rule>
  <sid>1000001</sid>
  <action>alert</action>
  <protocol>tcp</protocol>
  <source>any</source>
  <source_port>any</source_port>
  <destination>$HOME_NET</destination>
  <destination_port>22</destination_port>
  <options>msg:"SSH Connection Attempt"; flow:to_server,established; classtype:attempted-admin; sid:1000001; rev:1;</options>
</rule>

<rule>
  <sid>1000002</sid>
  <action>alert</action>
  <protocol>tcp</protocol>
  <source>any</source>
  <source_port>any</source_port>
  <destination>$HOME_NET</destination>
  <destination_port>445</destination_port>
  <options>msg:"SMB Connection Attempt"; flow:to_server,established; classtype:policy-violation; sid:1000002; rev:1;</options>
</rule>
```

### 3.3. VPN безопасность

#### 3.3.1. Требования к VPN
- **Протокол**: IKEv2/IPsec или SSL VPN
- **Аутентификация**: MFA обязательна
- **Шифрование**: AES-256 minimum
- **Сертификаты**: Клиентские сертификаты от корпоративного CA

#### 3.3.2. Конфигурация VPN
```cisco
! Пример конфигурации Cisco AnyConnect
crypto ikev2 proposal IKEV2-PROPOSAL
  encryption aes-cbc-256
  integrity sha256
  group 14
!
crypto ikev2 policy 10
  proposal IKEV2-PROPOSAL
!
crypto ikev2 enable outside
!
crypto ipsec transform-set ESP-AES256-SHA256 esp-aes-256 esp-sha256-hmac
  mode tunnel
!
crypto ipsec profile IPSEC-PROFILE
  set transform-set ESP-AES256-SHA256
!
tunnel-group VPN-GENERAL type remote-access
tunnel-group VPN-GENERAL general-attributes
  address-pool VPN-POOL
  default-group-policy VPN-POLICY
!
group-policy VPN-POLICY internal
group-policy VPN-POLICY attributes
  vpn-tunnel-protocol ikev2 ssl-clientless
  dns-server value 10.254.1.2 10.254.1.3
  default-domain-value dubaline.local
!
```

## 4. Безопасность внутренних сетей

### 4.1. Защита от внутренних угроз

#### 4.1.1. Принципы защиты
- **Минимизация привилегий**: Только необходимые права доступа
- **Сегментация**: Изоляция критичных систем
- **Мониторинг**: Постоянный контроль активности
- **Аудит**: Регулярная проверка прав доступа

#### 4.1.2. Технические меры
- **Private VLAN**: Изоляция пользователей в одном VLAN
- **Dynamic ARP Inspection**: Защита от ARP спуфинга
- **DHCP Snooping**: Защита от DHCP атак
- **IP Source Guard**: Проверка IP-MAC соответствия

### 4.2. Защита серверной инфраструктуры

#### 4.2.1. Сегментация серверов
```cisco
! VLAN для серверов
vlan 100
 name SRV-WEB-100
!
vlan 110
 name SRV-DB-110
!
vlan 120
 name SRV-APP-120
!
vlan 130
 name SRV-MGMT-130
!
! ACL для защиты серверов
ip access-list extended SRV-PROTECTION
 permit tcp host 10.2.100.10 host 10.2.110.20 eq 3306
 permit tcp host 10.2.100.11 host 10.2.110.21 eq 1433
 permit tcp any host 10.2.100.10 eq 80
 permit tcp any host 10.2.100.10 eq 443
 deny ip any any
!
interface Vlan100
 ip access-group SRV-PROTECTION in
```

#### 4.2.2. Защита баз данных
- **Изоляция**: Отдельный VLAN для баз данных
- **Ограниченный доступ**: Только с Application серверов
- **Шифрование**: Transparent Data Encryption
- **Аудит**: Логирование всех операций

### 4.3. Защита пользовательских сегментов

#### 4.3.1. Политики для пользователей
```cisco
! Ограничение P2P трафика
ip access-list extended USER-RESTRICTIONS
 deny tcp any any eq 1214
 deny udp any any eq 1214
 deny tcp any any eq 4662
 deny udp any any eq 4672
 deny tcp any any eq 6881
 deny udp any any eq 6881
 permit ip any any
!
interface Vlan30
 ip access-group USER-RESTRICTIONS in
!
! Ограничение скорости
policy-map USER-QOS
 class class-default
  shape average 10000000
  service-policy USER-RESTRICTIONS
```

#### 4.3.2. Контроль приложений
- **Application Visibility**: Мониторинг приложений
- **Application Control**: Блокировка запрещенных приложений
- **URL Filtering**: Фильтрация веб-сайтов
- **DLP Integration**: Предотвращение утечек данных

## 5. Безопасность беспроводных сетей

### 5.1. Архитектура Wi-Fi безопасности

#### 5.1.1. Требования к Wi-Fi
- **Протокол**: WPA3 Enterprise
- **Аутентификация**: 802.1X с RADIUS
- **Шифрование**: AES-256
- **Мониторинг**: Wireless Intrusion Detection

#### 5.1.2. Сегментация Wi-Fi сетей
- **Corporate Wi-Fi**: Для сотрудников с корпоративными устройствами
- **BYOD Wi-Fi**: Для личных устройств сотрудников
- **Guest Wi-Fi**: Для посетителей
- **IoT Wi-Fi**: Для устройств интернета вещей

### 5.2. Конфигурация Wi-Fi безопасности

#### 5.2.1. WLC конфигурация
```cisco
! Пример конфигурации Cisco WLC
! Создание WLAN
wlan Corporate-WiFi 1 Corporate-WiFi
 client vlan Vlan30
 security wpa wpa2
 security wpa wpa2 ciphers aes
 security wpa wpa2 authentication 8021x
!
! RADIUS серверы
radius server Dubalaine-RADIUS-1
 address ipv4 10.254.1.10 auth-port 1812 acct-port 1813
 key Dubalaine_Radius_Secret
!
radius server Dubalaine-RADIUS-2
 address ipv4 10.254.1.11 auth-port 1812 acct-port 1813
 key Dubalaine_Radius_Secret
!
! Групповая политика
wlan-policy Corporate-Policy
 wlan-id 1
 description "Corporate Wi-Fi Policy"
 qos silver
!
```

#### 5.2.2. Профили безопасности
```xml
<!-- Профиль для корпоративной сети -->
<WLANProfile>
  <name>Corporate-WiFi</name>
  <SSIDConfig>
    <SSID>
      <hex>436F72706F726174652D57694669</hex>
      <name>Corporate-WiFi</name>
    </SSID>
  </SSIDConfig>
  <connectionType>ESS</connectionType>
  <connectionMode>auto</connectionMode>
  <MSM>
    <security>
      <authEncryption>
        <authentication>WPA2Enterprise</authentication>
        <encryption>AES</encryption>
        <useOneX>true</useOneX>
      </authEncryption>
      <PMKCacheMode>enabled</PMKCacheMode>
      <PMKCacheTTL>7200</PMKCacheTTL>
      <PMKCacheSize>10</PMKCacheSize>
      <preAuthMode>disabled</preAuthMode>
      <oneX>
        <authMode>user</authMode>
        <EAPConfig>
          <EapHostConfig>
            <EapMethod>
              <Type xmlns="http://www.microsoft.com/provisioning/EapCommon">25</Type>
            </EapMethod>
          </EapHostConfig>
        </EAPConfig>
      </oneX>
    </security>
  </MSM>
</WLANProfile>
```

## 6. Мониторинг безопасности

### 6.1. SIEM система

#### 6.1.1. Источники событий
- **Network Devices**: Syslog от коммутаторов и маршрутизаторов
- **Firewalls**: Логи файрволов и IPS
- **Servers**: Windows Event Log, Linux syslog
- **Applications**: Логи приложений и баз данных
- **Authentication**: RADIUS, Active Directory логи

#### 6.1.2. Правила корреляции
```xml
<!-- Пример правил для Splunk -->
<rule name="Multiple Failed Login Attempts">
  <trigger>
    <condition>
      <field>event_type</field>
      <operator>equals</operator>
      <value>failed_login</value>
    </condition>
    <condition>
      <field>source_ip</field>
      <operator>equals</operator>
      <value>$source_ip$</value>
    </condition>
  </trigger>
  <threshold>
    <count>5</count>
    <time_window>5m</time_window>
  </threshold>
  <action>alert</action>
</rule>

<rule name="Privilege Escalation">
  <trigger>
    <condition>
      <field>event_type</field>
      <operator>equals</operator>
      <value>privilege_escalation</value>
    </condition>
  </trigger>
  <action>alert</action>
</rule>
```

### 6.2. Угрозы и аномалии

#### 6.2.1. Типы атак
- **DDoS**: Распределенные атаки отказа в обслуживании
- **APT**: Продвинутые постоянные угрозы
- **Insider Threat**: Внутренние угрозы
- **Malware**: Вредоносное ПО
- **Phishing**: Фишинговые атаки

#### 6.2.2. Индикаторы компрометации (IoC)
- **Network IoC**: Подозрительные IP адреса, домены
- **Host IoC**: Файлы, процессы, реестр
- **Behavioral IoC**: Аномальное поведение пользователей
- **Threat Intelligence**: Информация от внешних источников

### 6.3. Автоматический ответ

#### 6.3.1. SOAR платформа
- **Orchestration**: Координация действий между системами
- **Automation**: Автоматическое выполнение процедур
- **Response**: Стандартизированный ответ на инциденты

#### 6.3.2. Плейбуки реагирования
```yaml
# Пример плейбука для блокировки IP
name: Block Malicious IP
trigger:
  - type: siem_alert
    severity: high
    rule: "Malicious IP Detected"
actions:
  - name: block_ip_firewall
    type: firewall_block
    target: ip_address
    duration: 24h
    
  - name: block_ip_switch
    type: switch_acl
    target: ip_address
    action: deny
    
  - name: notify_admin
    type: email
    recipient: security-team@dubaline.ru
    subject: "IP Blocked: {{ ip_address }}"
    body: "IP {{ ip_address }} has been blocked due to malicious activity"
```

## 7. Управление инцидентами

### 7.1. Классификация инцидентов

#### 7.1.1. Уровни критичности
| Уровень | Описание | Время реакции | Время решения |
|--------|----------|---------------|--------------|
| Critical | Массовый сбой, угроза жизни | 15 минут | 4 часа |
| High | Значительное влияние на бизнес | 1 час | 8 часов |
| Medium | Ограниченное влияние | 4 часа | 24 часа |
| Low | Минимальное влияние | 24 часа | 72 часа |

#### 7.1.2. Типы инцидентов
- **Unauthorized Access**: Несанкционированный доступ
- **Malware**: Вредоносное ПО
- **DDoS**: Атаки отказа в обслуживании
- **Data Breach**: Утечка данных
- **Insider Threat**: Внутренние угрозы

### 7.2. Процедура реагирования

#### 7.2.1. Этапы реагирования
```
1. Detection (Обнаружение)
   - SIEM алерты
   - Сообщения пользователей
   - Автоматические системы обнаружения

2. Analysis (Анализ)
   - Определение масштаба
   - Идентификация источника
   - Оценка влияния

3. Containment (Сдерживание)
   - Изоляция затронутых систем
   - Блокировка атакующих
   - Предотвращение распространения

4. Eradication (Уничтожение)
   - Удаление вредоносного ПО
   - Закрытие уязвимостей
   - Восстановление систем

5. Recovery (Восстановление)
   - Восстановление из бэкапов
   - Тестирование систем
   - Возврат в нормальный режим

6. Lessons Learned (Анализ уроков)
   - Анализ причин
   - Обновление процедур
   - Обучение персонала
```

#### 7.2.2. Команда реагирования
- **Incident Commander**: Руководитель инцидента
- **Security Analyst**: Аналитик безопасности
- **Network Engineer**: Сетевой инженер
- **System Administrator**: Системный администратор
- **Legal Representative**: Юридический представитель
- **Communications Manager**: Менеджер коммуникаций

### 7.3. Коммуникации при инцидентах

#### 7.3.1. Внутренние коммуникации
- **Немедленно**: Команда реагирования
- **В течение 1 часа**: Руководство компании
- **В течение 4 часов**: Все затронутые отделы
- **В течение 24 часов**: Все сотрудники

#### 7.3.2. Внешние коммуникации
- **Регуляторы**: В соответствии с законодательством
- **Клиенты**: При утечке персональных данных
- **Партнеры**: При влиянии на их системы
- **Общественность**: При значительных инцидентах

## 8. Управление уязвимостями

### 8.1. Сканирование уязвимостей

#### 8.1.1. Регулярность сканирования
- **External Scan**: Еженедельно (внешняя периметр)
- **Internal Scan**: Ежемесячно (внутренняя сеть)
- **Authenticated Scan**: Ежеквартально (с учетными данными)
- **Web Application Scan**: Ежемесячно (веб-приложения)

#### 8.1.2. Классификация уязвимостей
| Уровень | Описание | Срок устранения |
|--------|----------|-----------------|
| Critical | Удаленное выполнение кода | 24 часа |
| High | Локальное повышение привилегий | 7 дней |
| Medium | DoS, информация disclosure | 30 дней |
| Low | Минимальные уязвимости | 90 дней |

### 8.2. Управление патчами

#### 8.2.1. Процесс патчирования
```
1. Assessment (Оценка)
   - Определение критичности уязвимости
   - Оценка влияния патча
   - Тестирование в лаборатории

2. Planning (Планирование)
   - Составление графика патчирования
   - Определение окна обслуживания
   - Подготовка плана отката

3. Deployment (Развертывание)
   - Создание бэкапов
   - Применение патчей
   - Проверка работоспособности

4. Verification (Проверка)
   - Проверка уязвимости
   - Тестирование функциональности
   - Мониторинг систем

5. Documentation (Документация)
   - Обновление CMDB
   - Отчет о патчировании
   - Анализ результатов
```

#### 8.2.2. Группы патчирования
- **Group 1 (Critical)**: Критичные системы, патчи в течение 24 часов
- **Group 2 (High)**: Важные системы, патчи в течение 7 дней
- **Group 3 (Medium)**: Обычные системы, патчи в течение 30 дней
- **Group 4 (Low)**: Второстепенные системы, патчи в течение 90 дней

## 9. Соответствие требованиям

### 9.1. Законодательные требования

#### 9.1.1. РФ законодательство
- **ФЗ-152**: О персональных данных
- **ФЗ-187**: О критической информационной инфраструктуре
- **ФЗ-99**: О защите государственной тайны
- **Приказ ФСТЭК**: Требования к защите информации

#### 9.1.2. Международные стандарты
- **ISO 27001**: Система менеджмента информационной безопасности
- **ISO 27002**: Кодекс практики информационной безопасности
- **PCI DSS**: Стандарт безопасности данных индустрии платежных карт
- **GDPR**: Общий регламент по защите данных

### 9.2. Аудит и комплаенс

#### 9.2.1. Внутренний аудит
- **Частота**: Ежеквартально
- **Область**: Все аспекты сетевой безопасности
- **Отчетность**: Руководству и Совету директоров

#### 9.2.2. Внешний аудит
- **Частота**: Ежегодно
- **Аудиторы**: Аккредитованные организации
- **Сертификация**: ISO 27001, PCI DSS

### 9.3. Отчетность и метрики

#### 9.3.1. Ключевые метрики безопасности
- **MTTR (Mean Time to Respond)**: Среднее время реагирования
- **MTTD (Mean Time to Detect)**: Среднее время обнаружения
- **Number of Incidents**: Количество инцидентов
- **Vulnerability Remediation Time**: Время устранения уязвимостей
- **Security Score**: Общий показатель безопасности

#### 9.3.2. Дашборды безопасности
- **Executive Dashboard**: Для руководства
- **Operational Dashboard**: для команды безопасности
- **Compliance Dashboard**: Для аудита и комплаенса

## 10. Обучение и осведомленность

### 10.1. Программа обучения

#### 10.1.1. Обязательное обучение
- **Новички**: Базовый курс безопасности (1 день)
- **Все сотрудники**: Ежегодное обучение (4 часа)
- **Администраторы**: Продвинутый курс (2 дня в квартал)
- **Руководители**: Управление рисками (1 день в полгода)

#### 10.1.2. Темы обучения
- **Основы безопасности**: Пароли, фишинг, социальная инженерия
- **Политики компании**: Правила использования ресурсов
- **Инциденты**: Как распознать и сообщить
- **Защита данных**: Классификация и обработка

### 10.2. Фишинговые симуляции

#### 10.2.1. Регулярность симуляций
- **Частота**: Ежеквартально
- **Покрытие**: Все сотрудники
- **Сложность**: Постепенное увеличение

#### 10.2.2. Процесс симуляции
```
1. Planning (Планирование)
   - Выбор типа фишинга
   - Определение целевой группы
   - Подготовка писем

2. Execution (Выполнение)
   - Отправка фишинговых писем
   - Мониторинг кликов
   - Сбор статистики

3. Analysis (Анализ)
   - Анализ результатов
   - Определение уязвимых групп
   - Подготовка отчета

4. Training (Обучение)
   - Дополнительное обучение для уязвимых
   - Общая информация для всех
   - Обновление политик
```

## 11. Приложения

### 11.1. Чек-лист безопасности нового устройства

```
□ Изменение паролей по умолчанию
□ Отключение неиспользуемых сервисов
□ Настройка ACL
□ Включение логирования
□ Настройка NTP
□ Настройка SNMPv3
□ Включение SSH, отключение Telnet
□ Настройка syslog
□ Настройка banner
□ Проверка уязвимостей
□ Ввод в эксплуатацию
```

### 11.2. Шаблон отчета об инциденте безопасности

```
Инцидент #: SEC-YYYY-MM-DD-XXX
Дата обнаружения: DD.MM.YYYY HH:MM
Дата начала: DD.MM.YYYY HH:MM
Дата завершения: DD.MM.YYYY HH:MM
Критичность: Critical/High/Medium/Low
Тип: Unauthorized Access/Malware/DDoS/Data Breach/Insider Threat
Описание: [Краткое описание инцидента]
Влияние: [Бизнес влияние]
Причина: [Корневая причина]
Действия: [Предпринятые действия]
Ущерб: [Финансовый и репутационный ущерб]
Уроки: [Извлеченные уроки]
Рекомендации: [Рекомендации по предотвращению]
```

### 11.3. Контактная информация службы безопасности

```
Экстренные ситуации (24/7):
- Security Operations Center: +7 (XXX) XXX-XX-XX
- CISO: +7 (XXX) XXX-XX-XX
- Incident Response Team: +7 (XXX) XXX-XX-XX

Рабочее время:
- Security Analyst: +7 (XXX) XXX-XX-XX
- Network Security Engineer: +7 (XXX) XXX-XX-XX
- Application Security: +7 (XXX) XXX-XX-XX

Внешние контакты:
- ФСТЭК: +7 (495) XXX-XX-XX
- CERT: +7 (495) XXX-XX-XX
- Правоохранительные органы: 102
```

---

**Документ версия**: 1.0  
**Дата последнего обновления**: 20.02.2026  
**Ответственный**: Chief Information Security Officer (CISO)  
**Периодичность пересмотра**: Ежегодно  
**Утверждено**: Советом директоров компании "Дубалайн"

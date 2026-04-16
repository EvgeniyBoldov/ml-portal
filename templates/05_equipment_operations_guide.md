# Руководство по эксплуатации сетевого оборудования
**Компания:** Дубалайн  
**Версия:** 1.0  
**Дата утверждения:** 20.02.2026  

---

## 1. Общие положения

### 1.1. Назначение руководства
Настоящее руководство определяет стандартные процедуры эксплуатации, обслуживания и мониторинга сетевого оборудования компании Дубалайн.

### 1.2. Область применения
Руководство распространяется на все сетевые устройства:
- Cisco Catalyst 9300/9500/9000 series
- Juniper EX/QFX series
- Arista 7000 series
- Системы управления и мониторинга

### 1.3. Уровни обслуживания
- **Уровень 1:** Базовое обслуживание (ежедневно)
- **Уровень 2:** Профилактическое обслуживание (еженедельно)
- **Уровень 3:** Капитальное обслуживание (ежеквартально)

---

## 2. Словарь терминов

| Термин | Определение |
|--------|------------|
| **Uptime** | Время непрерывной работы устройства |
| **MTBF** (Mean Time Between Failures) | Среднее время между отказами |
| **MTTR** (Mean Time To Repair) | Среднее время восстановления |
| **Firmware** | Встроенное ПО устройства |
| **IOS** (Internetwork Operating System) | Операционная система Cisco |
| **JunOS** | Операционная система Juniper |
| **EOS** (Extensible Operating System) | Операционная система Arista |
| **PoE** (Power over Ethernet) | Питание по Ethernet |
| **VLAN** (Virtual LAN) | Виртуальная локальная сеть |
| **STP** (Spanning Tree Protocol) | Протокол остовного дерева |

---

## 3. Ежедневные операции

### 3.1. Утренняя проверка (08:00)

#### Чек-лист проверки состояния
```bash
# 1. Проверка доступности устройств
for device in $(cat devices_list.txt); do
    ping -c 3 $device
done

# 2. Проверка загрузки CPU
ssh admin@switch "show processes cpu sorted | include 0.00"

# 3. Проверка использования памяти
ssh admin@switch "show memory statistics"

# 4. Проверка температуры
ssh admin@switch "show environment temperature"

# 5. Проверка питания
ssh admin@switch "show environment power"
```

#### Пример отчета
```
Ежедневный отчет о состоянии сети
Дата: 20.02.2026 08:30
Оператор: Иван Петров

Устройств в сети: 45/45 (100%)
Критичных алертов: 0
Предупреждений: 2
Температура в норме: 44/44 (100%)
Питание в норме: 45/45 (100%)

Требуется внимание:
- SW-CORE-02: Высокая загрузка CPU (75%)
- SW-ACC-15: Низкий уровень PoE на порту 23
```

### 3.2. Вечерняя проверка (20:00)

#### Проверка логов
```bash
# Сбор логов за день
for device in $(cat critical_devices.txt); do
    ssh admin@$device "show logging | include Feb 20"
done > daily_logs_$(date +%Y%m%d).txt

# Поиск критичных событий
grep -i "error\|fail\|down\|critical" daily_logs_$(date +%Y%m%d).txt
```

#### Архивирование конфигураций
```python
#!/usr/bin/env python3
import paramiko
import datetime
import os

def backup_configs():
    devices = load_device_list()
    backup_dir = f"/backups/configs/{datetime.date.today()}"
    
    for device in devices:
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(device['ip'], username='admin', password='password')
            
            stdin, stdout, stderr = ssh.exec_command("show running-config")
            config = stdout.read().decode()
            
            with open(f"{backup_dir}/{device['hostname']}.cfg", 'w') as f:
                f.write(config)
                
            ssh.close()
        except Exception as e:
            log_error(f"Failed to backup {device['hostname']}: {e}")

if __name__ == "__main__":
    backup_configs()
```

---

## 4. Еженедельные операции

### 4.1. Профилактическое обслуживание

#### Проверка обновлений ПО
```bash
# Проверка доступных обновлений
for device in $(cat all_devices.txt); do
    echo "Checking $device:"
    ssh admin@$device "show version | include Version"
done

# Проверка рекомендованных версий
curl -s "https://software.cisco.com/download/api/v1/recommended" | \
jq '.recommendations[] | select(.platform=="Catalyst 9500")'
```

#### Очистка логов
```cisco
# На Cisco устройствах
configure terminal
no logging event-link-status
logging persistent
file flash:log.txt
exit
clear logging
```

#### Проверка интерфейсов
```bash
#!/bin/bash
# Проверка состояния интерфейсов
for device in $(cat devices_list.txt); do
    echo "=== $device ==="
    ssh admin@$device "show interface status | include connected"
    ssh admin@$device "show interface counters | include errors"
done
```

### 4.2. Анализ производительности

#### Мониторинг загрузки
```python
def analyze_weekly_performance():
    metrics = {
        'cpu_usage': [],
        'memory_usage': [],
        'interface_errors': [],
        'temperature': []
    }
    
    for day in range(7):
        date = datetime.date.today() - datetime.timedelta(days=day)
        daily_metrics = load_daily_metrics(date)
        
        for metric in metrics:
            metrics[metric].extend(daily_metrics.get(metric, []))
    
    return generate_performance_report(metrics)
```

---

## 5. Ежеквартальные операции

### 5.1. Капитальное обслуживание

#### Проверка физического состояния
```
Чек-лист физического осмотра:

[ ] Визуальный осмотр оборудования
[ ] Проверка вентиляторов и охлаждения
[ ] Очистка от пыли
[ ] Проверка кабельных соединений
[ ] Тестирование портов
[ ] Проверка индикаторов
[ ] Измерение напряжения питания
[ ] Тестирование резервных блоков питания
```

#### Обновление прошивки
```bash
# Процедура обновления Cisco IOS
#!/bin/bash
DEVICE="192.168.1.100"
IMAGE="cat9k_iosxe.17.09.04.SPA.bin"
TFTP_SERVER="192.168.1.50"

# 1. Проверка свободного места
ssh admin@$DEVICE "dir flash: | include bytes"

# 2. Копирование образа
ssh admin@$DEVICE "copy tftp://$TFTP_SERVER/$IMAGE flash:"

# 3. Проверка целостности
ssh admin@$DEVICE "verify /md5 flash:$IMAGE"

# 4. Установка boot variable
ssh admin@$DEVICE "configure terminal"
ssh admin@$DEVICE "boot system flash:$IMAGE"
ssh admin@$DEVICE "exit"

# 5. Сохранение конфигурации
ssh admin@$DEVICE "write memory"

# 6. Перезагрузка (с подтверждением)
echo "Ready to reboot $DEVICE. Confirm? [y/N]"
read confirm
if [[ $confirm == "y" ]]; then
    ssh admin@$DEVICE "reload"
fi
```

### 5.2. Тестирование отказоустойчивости

#### Тестирование избыточности
```python
def test_redundancy():
    test_cases = [
        {
            'name': 'Core Switch Failover',
            'primary': 'core-01',
            'backup': 'core-02',
            'test': shutdown_interface
        },
        {
            'name': 'Power Supply Failover',
            'device': 'dist-01',
            'test': shutdown_power_supply
        },
        {
            'name': 'Link Aggregation Failover',
            'device': 'acc-01',
            'test': shutdown_lag_member
        }
    ]
    
    results = []
    for test in test_cases:
        result = execute_test(test)
        results.append(result)
        
        # Возврат в нормальное состояние
        restore_normal_state(test)
    
    return generate_test_report(results)
```

---

## 6. Обслуживание конкретного оборудования

### 6.1. Cisco Catalyst 9300 Series

#### Базовая конфигурация
```cisco
! Основные настройки
hostname SW-ACC-FLOOR1-01
!
! Настройка управления
interface Vlan1
 ip address 192.168.1.10 255.255.255.0
 no shutdown
!
! Настройка NTP
ntp server 192.168.1.100
!
! Настройка SNMP
snmp-server community DubalaineRO RO
snmp-server location "Floor 1 Rack 1"
snmp-server contact "Network Team"
!
! Настройка syslog
logging host 192.168.1.200
logging trap informational
!
! Настройка PoE
interface range GigabitEthernet1/0/1-24
 power inline auto
!
```

#### Диагностика проблем
```cisco
! Проверка проблем с портами
show interface status
show interface counters errors
show logging | include Interface

! Проверка проблем с PoE
show power inline
show power inline consumption
show logging | include POE

! Проверка проблем с VLAN
show vlan brief
show interface trunk
show spanning-tree vlan
```

### 6.2. Cisco Catalyst 9500 Series

#### Конфигурация Layer 3
```cisco
! Включение routing
ip routing
!
! Создание SVI
interface Vlan10
 description Management VLAN
 ip address 10.0.10.1 255.255.255.0
 no shutdown
!
interface Vlan20
 description Servers VLAN
 ip address 10.0.20.1 255.255.255.0
 no shutdown
!
! Настройка OSPF
router ospf 1
 router-id 10.0.10.1
 network 10.0.10.0 0.0.0.255 area 0
 network 10.0.20.0 0.0.0.255 area 0
!
```

#### Мониторинг производительности
```cisco
! Проверка загрузки CPU
show processes cpu sorted | exclude 0.00%

! Проверка использования памяти
show memory statistics | include Total

! Проверка таблицы маршрутизации
show ip route summary
show ip ospf neighbor

! Проверка ASIC utilization
show platform hardware fed active switch 1 qos statistics
```

### 6.3. Juniper EX Series

#### Базовая конфигурация
```junos
# set system host-name SW-ACC-FLOOR1-02
# set system root-authentication encrypted-password "password"
# set system services ssh
# set system services telnet
# set system services netconf ssh
# set system ntp server 192.168.1.100
#
# set interfaces vlan unit 0 family inet address 192.168.1.11/24
# set vlans default vlan-id 1
# set vlans default l3-interface vlan.0
#
# set system syslog host 192.168.1.200 any any
# set system snmp community DubalaineRO authorization read-only
```

#### Диагностика
```junos
# Проверка состояния интерфейсов
show interfaces extensive | match "Physical interface|Last flapped"

# Проверка маршрутизации
show route summary
show ospf neighbor

# Проверка системных ресурсов
show chassis routing-engine
show system processes extensive
```

---

## 7. Мониторинг и алерты

### 7.1. Система мониторинга

#### Prometheus конфигурация
```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'cisco_switches'
    static_configs:
      - targets: ['192.168.1.10:9106', '192.168.1.11:9106']
    metrics_path: /snmp
    params:
      module: [cisco]
    relabel_configs:
      - source_labels: [__address__]
        target_label: __param_target
      - source_labels: [__param_target]
        target_label: instance
      - target_label: __address__
        replacement: 127.0.0.1:9116
```

#### Правила алертов
```yaml
groups:
- name: network_equipment
  rules:
  - alert: HighCPUUsage
    expr: cisco_cpu_usage > 80
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "High CPU usage on {{ $labels.instance }}"
      description: "CPU usage is {{ $value }}% on {{ $labels.instance }}"

  - alert: InterfaceDown
    expr: ifOperStatus != 1
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "Interface {{ $labels.ifDescr }} is down on {{ $labels.instance }}"
```

### 7.2. Grafana дашборды

#### Метрики для дашборда
```json
{
  "dashboard": {
    "title": "Network Equipment Status",
    "panels": [
      {
        "title": "CPU Usage",
        "type": "graph",
        "targets": [
          {
            "expr": "cisco_cpu_usage{instance=~\"SW-.*\"}",
            "legendFormat": "{{instance}}"
          }
        ]
      },
      {
        "title": "Memory Usage",
        "type": "graph",
        "targets": [
          {
            "expr": "cisco_memory_usage{instance=~\"SW-.*\"}",
            "legendFormat": "{{instance}}"
          }
        ]
      },
      {
        "title": "Interface Status",
        "type": "table",
        "targets": [
          {
            "expr": "ifOperStatus{instance=~\"SW-.*\"}",
            "format": "table"
          }
        ]
      }
    ]
  }
}
```

---

## 8. Безопасность обслуживания

### 8.1. Доступ к оборудованию

#### Управление доступом
```cisco
! Создание пользователей с разными уровнями доступа
username admin privilege 15 secret AdminPass123
username operator privilege 5 secret OperPass123
username readonly privilege 1 secret ReadPass123

! Настройка AAA
aaa new-model
aaa authentication login default local
aaa authorization exec default local
aaa accounting exec default start-stop group radius

! Настройка RADIUS
radius server DUBALAINE-RADIUS
 address ipv4 192.168.1.100 auth-port 1812 acct-port 1813
 key DubalaineRadiusKey
```

#### SSH безопасность
```cisco
! Настройка SSH
ip ssh version 2
ip ssh authentication-retries 3
ip ssh time-out 60
!
! Ограничение доступа по IP
access-list 10 permit 192.168.1.0 0.0.0.255
access-list 10 deny any
!
line vty 0 4
 access-class 10 in
 transport input ssh
 login local
!
```

### 8.2. Аудит и логирование

#### Сбор логов
```python
def collect_security_logs():
    security_events = [
        'login failures',
        'configuration changes',
        'privilege escalations',
        'interface state changes'
    ]
    
    for device in get_all_devices():
        logs = ssh_execute(device, 'show logging')
        security_logs = filter_security_events(logs, security_events)
        store_security_logs(device, security_logs)
```

#### Анализ безопасности
```bash
#!/bin/bash
# Анализ логов безопасности
grep -i "failed login\|unauthorized\|security" /var/log/network/*.log | \
awk '{print $1, $2, $3, $NF}' | \
sort | uniq -c | sort -nr > security_report.txt

# Проверка изменений конфигурации
grep -i "config\|changed\|modified" /var/log/network/config_changes.log | \
tail -50 > recent_changes.txt
```

---

## 9. Процедуры замены оборудования

### 9.1. Плановая замена

#### Подготовка к замене
```
Чек-лист подготовки:

[ ] Создать backup конфигурации
[ ] Подготовить новое оборудование
[ ] Запланировать время простоя
[ ] Уведомить пользователей
[ ] Подготовить кабели и инструменты
[ ] Проверить совместимость ПО
[ ] Создать план отката
```

#### Процедура замены
```bash
#!/bin/bash
# Скрипт замены access switch
OLD_SWITCH="192.168.1.50"
NEW_SWITCH="192.168.1.51"

# 1. Сохранение конфигурации старого свитча
ssh admin@$OLD_SWITCH "show running-config" > old_switch_config.cfg

# 2. Применение конфигурации на новом свитче
scp old_switch_config.cfg admin@$NEW_SWITCH:/flash/
ssh admin@$NEW_SWITCH "configure replace flash:old_switch_config.cfg force"

# 3. Проверка конфигурации
ssh admin@$NEW_SWITCH "show running-config | diff startup-config"

# 4. Сохранение конфигурации
ssh admin@$NEW_SWITCH "write memory"

# 5. Тестирование подключений
for port in {1..24}; do
    ping -c 1 192.168.1.$((100+$port))
done
```

### 9.2. Аварийная замена

#### Процедура экстренной замены
```
Время: 0-15 минут
1. Оценка ситуации
2. Извлечение резервного оборудования
3. Базовая конфигурация
4. Подключение критичных сервисов
5. Постепенная настройка остальных сервисов

Время: 15-60 минут
6. Полная настройка
7. Тестирование
8. Возврат к нормальной работе
```

---

## 10. Оптимизация производительности

### 10.1. Настройка QoS

#### Приоритизация трафика
```cisco
! Создание классов трафика
class-map VOICE
 match dscp ef
!
class-map VIDEO
 match dscp af41
!
class-map BUSINESS
 match dscp af21
!
! Создание политик
policy-map QOS-POLICY
 class VOICE
  priority percent 30
 class VIDEO
  bandwidth percent 25
 class BUSINESS
  bandwidth percent 35
 class class-default
  fair-queue
!
! Применение политик
interface range GigabitEthernet1/0/1-24
 service-policy output QOS-POLICY
```

### 10.2. Оптимизация маршрутизации

#### Настройка OSPF
```cisco
router ospf 1
 router-id 10.0.0.1
 passive-interface default
 no passive-interface GigabitEthernet1/0/1
 no passive-interface GigabitEthernet1/0/2
!
 interface GigabitEthernet1/0/1
 ip ospf cost 10
 ip ospf priority 100
!
 interface GigabitEthernet1/0/2
 ip ospf cost 20
 ip ospf priority 50
```

---

## 11. Документация и отчетность

### 11.1. Ведение документации

#### Структура документации
```
/network-documentation/
├── equipment/
│   ├── inventory/
│   ├── configurations/
│   └── maintenance-logs/
├── network-maps/
│   ├── logical/
│   └── physical/
├── procedures/
│   ├── daily/
│   ├── weekly/
│   └── quarterly/
└── reports/
    ├── daily/
    ├── weekly/
    └── monthly/
```

#### Автоматическая генерация отчетов
```python
def generate_daily_report():
    report_data = {
        'date': datetime.date.today(),
        'uptime': calculate_uptime(),
        'alerts': get_active_alerts(),
        'changes': get_configuration_changes(),
        'performance': get_performance_metrics()
    }
    
    template = load_template('daily_report.html')
    report = render_template(template, report_data)
    
    save_report(f"/reports/daily/report_{datetime.date.today()}.html", report)
    send_report_email(report)
```

### 11.2. Анализ метрик

#### KPI для сетевого оборудования
```
Доступность: > 99.99%
Время отклика: < 1ms
Загрузка CPU: < 70%
Использование памяти: < 80%
Количество ошибок: < 0.1%
Время восстановления: < 15 минут
```

---

## 12. Обучение персонала

### 12.1. Программа обучения

| Тема | Уровень | Длительность | Требования |
|------|---------|--------------|------------|
| Основы Cisco IOS | Базовый | 8 часов | Нет |
| Продвинутая конфигурация | Средний | 16 часов | Базовый |
| Траблшутинг | Продвинутый | 24 часа | Средний |
| Безопасность сетей | Средний | 12 часов | Базовый |

### 12.2. Практические задания

#### Лабораторная работа 1: Базовая настройка
```
Задание:
1. Подключиться к оборудованию
2. Настроить hostname
3. Настроить управление
4. Настроить NTP
5. Сохранить конфигурацию

Проверка:
- Ping от устройства к gateway
- Доступ по SSH
- Синхронизация времени
```

---

## 13. Приложения

### Приложение A: Команды быстрой диагностики

```bash
# Cisco
show version                    # Версия ПО и uptime
show running-config            # Текущая конфигурация
show interfaces status         # Статус интерфейсов
show processes cpu             # Загрузка CPU
show memory statistics         # Использование памяти
show environment               # Температура и питание
show logging                   # Системные логи

# Juniper
show version                   # Версия ПО
show configuration             # Конфигурация
show interfaces terse          # Статус интерфейсов
show chassis routing-engine    # Загрузка CPU
show system virtual-memory      # Использование памяти
show chassis environment       # Температура и питание
show log messages              # Системные логи
```

### Приложение B: Таблица портов и подключений

```
SW-ACC-FLOOR1-01:
Port | VLAN | Device | Status | Notes
-----|------|--------|--------|-------
Gi1/0/1 | 10 | PC-001 | Up | User workstation
Gi1/0/2 | 10 | PC-002 | Up | User workstation
Gi1/0/3 | 20 | SRV-001 | Up | Application server
Gi1/0/4 | 30 | PRN-001 | Up | Network printer
```

### Приложение C: Контакты поставщиков

```
Cisco Support:
Телефон: 8-800-700-6750
Email: support-russia@cisco.com
Chat: https://cisco.com/support

Juniper Support:
Телефон: 8-800-700-6751
Email: support-russia@juniper.net
Chat: https://juniper.net/support
```

---

## 14. История изменений

| Версия | Дата | Изменения | Автор |
|--------|------|-----------|-------|
| 1.0 | 20.02.2026 | Первая версия документа | Network Team |
| | | | |

---

**Документ утвержден:**

_________________________ / Иван Петров /
Lead Network Engineer

_________________________ / Мария Иванова /
Senior Network Engineer

_________________________ / Алексей Сидоров /
Network Administrator

---

*Документ является конфиденциальной собственностью компании Дубалайн. Распространение запрещено.*

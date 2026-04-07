import { useState, useEffect, useCallback, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import {
  Save,
  RotateCcw,
  Download,
  Upload,
  Cpu,
  Thermometer,
  HardDrive,
  MemoryStick,
} from 'lucide-react';
import { configApi, healthApi } from '../services/api';
import LoadingSpinner from '../components/LoadingSpinner';
import type { SystemConfig } from '../types';

// ============================================================
// Slider component
// ============================================================

function ThresholdSlider({
  label,
  value,
  min,
  max,
  step,
  onChange,
  unit = '',
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (val: number) => void;
  unit?: string;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium text-dark">{label}</label>
        <span className="text-sm font-bold text-primary tabular-nums">
          {value}{unit}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-primary"
      />
      <div className="flex justify-between text-xs text-dark-lighter">
        <span>{min}{unit}</span>
        <span>{max}{unit}</span>
      </div>
    </div>
  );
}

// ============================================================
// Main Component
// ============================================================

function SettingsPage() {
  const queryClient = useQueryClient();
  const restoreInputRef = useRef<HTMLInputElement>(null);

  const [localConfig, setLocalConfig] = useState<SystemConfig | null>(null);
  const [hasChanges, setHasChanges] = useState(false);

  // Queries
  const { data: configRes, isLoading: configLoading } = useQuery({
    queryKey: ['config'],
    queryFn: configApi.get,
  });

  const { data: healthRes } = useQuery({
    queryKey: ['health'],
    queryFn: healthApi.get,
    refetchInterval: 10_000,
  });

  const healthData = healthRes?.data;

  // Initialize local config from server
  useEffect(() => {
    if (configRes?.data && !localConfig) {
      setLocalConfig(configRes.data);
    }
  }, [configRes, localConfig]);

  // Mutations
  const updateMutation = useMutation({
    mutationFn: configApi.update,
    onSuccess: () => {
      toast.success('Settings saved');
      setHasChanges(false);
      queryClient.invalidateQueries({ queryKey: ['config'] });
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const backupMutation = useMutation({
    mutationFn: configApi.backup,
    onSuccess: (res) => {
      toast.success(`Backup created: ${res.data?.filename ?? 'success'}`);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const restoreMutation = useMutation({
    mutationFn: configApi.restore,
    onSuccess: () => {
      toast.success('Configuration restored');
      queryClient.invalidateQueries({ queryKey: ['config'] });
      setLocalConfig(null);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const updateField = useCallback(
    <K extends keyof SystemConfig>(field: K, value: SystemConfig[K]) => {
      setLocalConfig((prev) => (prev ? { ...prev, [field]: value } : prev));
      setHasChanges(true);
    },
    [],
  );

  const handleSave = useCallback(() => {
    if (!localConfig) return;
    updateMutation.mutate({
      verify_threshold: localConfig.verify_threshold,
      identify_threshold: localConfig.identify_threshold,
      identify_top_k: localConfig.identify_top_k,
      debug: localConfig.debug,
    });
  }, [localConfig, updateMutation]);

  const handleReset = useCallback(() => {
    if (configRes?.data) {
      setLocalConfig(configRes.data);
      setHasChanges(false);
    }
  }, [configRes]);

  const handleRestoreFile = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) restoreMutation.mutate(file);
    },
    [restoreMutation],
  );

  if (configLoading || !localConfig) {
    return <LoadingSpinner size="lg" className="mt-20" />;
  }

  const memoryPercent = healthData
    ? (healthData.memory_used_mb / healthData.memory_total_mb * 100)
    : 0;
  const diskPercent = healthData
    ? (healthData.disk_used_gb / healthData.disk_total_gb * 100)
    : 0;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Save bar */}
      {hasChanges && (
        <div className="card bg-primary/5 border-primary/20 flex items-center justify-between">
          <p className="text-sm font-medium text-primary">You have unsaved changes</p>
          <div className="flex items-center gap-2">
            <button onClick={handleReset} className="btn-outline text-sm py-1.5">
              <RotateCcw size={16} />
              Reset
            </button>
            <button
              onClick={handleSave}
              disabled={updateMutation.isPending}
              className="btn-primary text-sm py-1.5"
            >
              {updateMutation.isPending ? <LoadingSpinner size="sm" /> : <Save size={16} />}
              Save
            </button>
          </div>
        </div>
      )}

      {/* Thresholds */}
      <div className="card space-y-5">
        <h3 className="text-base font-semibold text-dark">Thresholds</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <ThresholdSlider
            label="Verification Threshold"
            value={localConfig.verify_threshold}
            min={0}
            max={1}
            step={0.01}
            onChange={(v) => updateField('verify_threshold', v)}
          />
          <ThresholdSlider
            label="Identification Threshold"
            value={localConfig.identify_threshold}
            min={0}
            max={1}
            step={0.01}
            onChange={(v) => updateField('identify_threshold', v)}
          />
          <div>
            <label className="block text-sm font-medium text-dark-lighter mb-1">
              Identify Top K
            </label>
            <input
              type="number"
              value={localConfig.identify_top_k}
              onChange={(e) => updateField('identify_top_k', Number(e.target.value))}
              className="input-field"
              min={1}
              max={50}
            />
          </div>
          <div className="flex items-center gap-3">
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={localConfig.debug}
                onChange={(e) => updateField('debug', e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-primary/40 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary" />
            </label>
            <span className="text-sm font-medium text-dark">Debug Mode</span>
          </div>
        </div>
      </div>

      {/* System info (read-only from config) */}
      <div className="card space-y-4">
        <h3 className="text-base font-semibold text-dark">System Info</h3>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="text-xs text-dark-lighter">Device ID</span>
            <p className="font-medium text-dark">{localConfig.device_id}</p>
          </div>
          <div>
            <span className="text-xs text-dark-lighter">Model Directory</span>
            <p className="font-medium text-dark truncate">{localConfig.model_dir}</p>
          </div>
          <div>
            <span className="text-xs text-dark-lighter">Data Directory</span>
            <p className="font-medium text-dark truncate">{localConfig.data_dir}</p>
          </div>
          <div>
            <span className="text-xs text-dark-lighter">Sensor</span>
            <p className="font-medium text-dark">
              VID: 0x{localConfig.sensor_vid.toString(16).toUpperCase().padStart(4, '0')}{' '}
              PID: 0x{localConfig.sensor_pid.toString(16).toUpperCase().padStart(4, '0')}
            </p>
          </div>
        </div>
      </div>

      {/* Device info from health */}
      {healthData && (
        <div className="card space-y-4">
          <h3 className="text-base font-semibold text-dark">Device Status</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <DeviceInfoCard
              icon={Cpu}
              label="CPU Usage"
              value={`${healthData.cpu_percent.toFixed(1)}%`}
              color={healthData.cpu_percent > 80 ? 'danger' : healthData.cpu_percent > 50 ? 'warning' : 'success'}
            />
            <DeviceInfoCard
              icon={MemoryStick}
              label="Memory"
              value={`${memoryPercent.toFixed(1)}%`}
              color={memoryPercent > 80 ? 'danger' : memoryPercent > 50 ? 'warning' : 'success'}
            />
            <DeviceInfoCard
              icon={HardDrive}
              label="Disk"
              value={`${diskPercent.toFixed(1)}%`}
              color={diskPercent > 80 ? 'danger' : diskPercent > 50 ? 'warning' : 'success'}
            />
            <DeviceInfoCard
              icon={Thermometer}
              label="Temperature"
              value={healthData.cpu_temp_c ? `${healthData.cpu_temp_c.toFixed(0)}C` : 'N/A'}
              color={
                healthData.cpu_temp_c
                  ? healthData.cpu_temp_c > 70 ? 'danger' : healthData.cpu_temp_c > 50 ? 'warning' : 'success'
                  : 'primary'
              }
            />
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm text-dark-lighter">
            <div>
              <span className="text-xs">Device ID:</span>
              <p className="font-medium text-dark">{healthData.device_id}</p>
            </div>
            <div>
              <span className="text-xs">Active Model:</span>
              <p className="font-medium text-dark">{healthData.active_model ?? 'None'}</p>
            </div>
          </div>
        </div>
      )}

      {/* Database / Backup Restore */}
      <div className="card space-y-4">
        <h3 className="text-base font-semibold text-dark">Database</h3>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() => backupMutation.mutate()}
            disabled={backupMutation.isPending}
            className="btn-primary"
          >
            {backupMutation.isPending ? <LoadingSpinner size="sm" /> : <Download size={18} />}
            Backup Now
          </button>
          <button
            onClick={() => restoreInputRef.current?.click()}
            disabled={restoreMutation.isPending}
            className="btn-outline"
          >
            {restoreMutation.isPending ? <LoadingSpinner size="sm" /> : <Upload size={18} />}
            Restore
          </button>
          <input
            ref={restoreInputRef}
            type="file"
            accept=".json,.db,.sqlite,.bak"
            onChange={handleRestoreFile}
            className="hidden"
          />
        </div>
      </div>
    </div>
  );
}

function DeviceInfoCard({
  icon: Icon,
  label,
  value,
  color,
}: {
  icon: typeof Cpu;
  label: string;
  value: string;
  color: 'primary' | 'success' | 'warning' | 'danger';
}) {
  const colorMap = {
    primary: 'text-primary bg-primary/10',
    success: 'text-success bg-success/10',
    warning: 'text-warning bg-warning/10',
    danger: 'text-danger bg-danger/10',
  };

  return (
    <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
      <div className={`p-2 rounded-lg ${colorMap[color]}`}>
        <Icon size={18} />
      </div>
      <div>
        <p className="text-xs text-dark-lighter">{label}</p>
        <p className="font-bold text-dark">{value}</p>
      </div>
    </div>
  );
}

export default SettingsPage;

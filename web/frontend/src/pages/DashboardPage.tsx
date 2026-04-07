import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Users,
  ScanLine,
  CheckCircle,
  Clock,
  UserPlus,
  Fingerprint,
} from 'lucide-react';
import { statsApi, logsApi } from '../services/api';
import StatsCard from '../components/StatsCard';
import LoadingSpinner from '../components/LoadingSpinner';
import type { LogEntry } from '../types';

function DashboardPage() {
  const navigate = useNavigate();

  const { data: statsRes, isLoading: statsLoading } = useQuery({
    queryKey: ['stats'],
    queryFn: statsApi.get,
    refetchInterval: 30_000,
  });

  const { data: logsRes, isLoading: logsLoading } = useQuery({
    queryKey: ['logs', 'recent'],
    queryFn: () => logsApi.list({ page: 1, limit: 20 }),
    refetchInterval: 15_000,
  });

  const stats = statsRes?.data;
  const logs = logsRes?.data?.logs ?? [];

  if (statsLoading) {
    return <LoadingSpinner size="lg" className="mt-20" />;
  }

  return (
    <div className="space-y-6">
      {/* Stats cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <StatsCard
          icon={Users}
          label="Enrolled Users"
          value={stats?.enrolled_users ?? 0}
          color="primary"
        />
        <StatsCard
          icon={ScanLine}
          label="Verifications Today"
          value={stats?.verifications_today ?? 0}
          color="success"
        />
        <StatsCard
          icon={CheckCircle}
          label="Acceptance Rate"
          value={`${(stats?.acceptance_rate ?? 0).toFixed(1)}%`}
          color="warning"
        />
        <StatsCard
          icon={Clock}
          label="Avg Latency"
          value={`${(stats?.avg_latency_ms ?? 0).toFixed(0)}ms`}
          color="danger"
        />
      </div>

      {/* Quick actions */}
      <div className="flex flex-wrap gap-3">
        <button onClick={() => navigate('/enroll')} className="btn-primary">
          <UserPlus size={18} />
          New Enrollment
        </button>
        <button onClick={() => navigate('/verify')} className="btn-success">
          <Fingerprint size={18} />
          Start Verification
        </button>
      </div>

      {/* Additional stats */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="card text-center">
          <p className="text-2xl font-bold text-primary">{stats?.enrolled_fingers ?? 0}</p>
          <p className="text-sm text-dark-lighter mt-1">Enrolled Fingers</p>
        </div>
        <div className="card text-center">
          <p className="text-2xl font-bold text-primary">{stats?.identifications_today ?? 0}</p>
          <p className="text-sm text-dark-lighter mt-1">Identifications Today</p>
        </div>
        <div className="card text-center">
          <p className="text-2xl font-bold text-primary">{(stats?.rejection_rate ?? 0).toFixed(1)}%</p>
          <p className="text-sm text-dark-lighter mt-1">Rejection Rate</p>
        </div>
      </div>

      {/* Recent logs */}
      <div className="card">
        <h3 className="text-base font-semibold text-dark mb-4">
          Recent Verification Logs
        </h3>
        {logsLoading ? (
          <LoadingSpinner />
        ) : logs.length === 0 ? (
          <p className="text-center text-dark-lighter py-8">No logs yet</p>
        ) : (
          <div className="overflow-x-auto -mx-5">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-100">
                  <th className="px-5 py-2.5 text-left font-semibold text-dark-lighter">Time</th>
                  <th className="px-5 py-2.5 text-left font-semibold text-dark-lighter">Employee</th>
                  <th className="px-5 py-2.5 text-left font-semibold text-dark-lighter">Action</th>
                  <th className="px-5 py-2.5 text-left font-semibold text-dark-lighter">Decision</th>
                  <th className="px-5 py-2.5 text-left font-semibold text-dark-lighter">Score</th>
                  <th className="px-5 py-2.5 text-left font-semibold text-dark-lighter">Latency</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log: LogEntry) => (
                  <tr key={log.id} className="border-b border-gray-50 last:border-0">
                    <td className="px-5 py-2.5 text-dark-lighter whitespace-nowrap">
                      {new Date(log.timestamp).toLocaleTimeString()}
                    </td>
                    <td className="px-5 py-2.5">{log.employee_id ?? 'Unknown'}</td>
                    <td className="px-5 py-2.5">
                      <span className="capitalize">{log.action}</span>
                    </td>
                    <td className="px-5 py-2.5">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
                          log.decision === 'accept'
                            ? 'bg-success/10 text-success-dark'
                            : log.decision === 'error'
                            ? 'bg-warning/10 text-warning-dark'
                            : 'bg-danger/10 text-danger-dark'
                        }`}
                      >
                        {log.decision.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-5 py-2.5">
                      {log.score !== null ? `${(log.score * 100).toFixed(1)}%` : '-'}
                    </td>
                    <td className="px-5 py-2.5">
                      {log.latency_ms !== null ? `${log.latency_ms.toFixed(0)}ms` : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export default DashboardPage;

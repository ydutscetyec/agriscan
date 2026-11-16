import { useEffect, useState } from 'react'
import { Boxes } from 'lucide-react'
import { api } from '../api/client'
import { PageHeader } from '../components/Layout'

/** Read-only. Models are never edited from the dashboard: a model version that can be
 *  changed in a browser cannot be cited in a results table. */
export default function Models() {
  const [models, setModels] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    api.models().then(setModels).catch((e) => setError(e.message))
  }, [])

  return (
    <div className="as-content">
      <PageHeader
        eyebrow="Administration"
        icon={Boxes} title="Model registry" description="Every detection names the model that produced it. Registry entries are never overwritten or deleted, so an old result stays traceable after a retrain." />

      {error && <div className="as-warn">{error}</div>}

      {models.length === 0 ? (
        <div className="as-empty">No models registered.</div>
      ) : (
        <table className="as-table">
          <thead>
            <tr>
              <th>Name</th><th>Architecture</th><th>Imaging</th><th>Dataset</th>
              <th>Trained</th><th>Deployment</th><th>Capability</th><th>Metrics</th>
            </tr>
          </thead>
          <tbody>
            {models.map((m) => (
              <tr key={m.id}>
                <td style={{ fontWeight: 600 }}>{m.name}</td>
                <td>{m.architecture}</td>
                <td>{m.imaging_mode}</td>
                <td>{m.dataset_version}</td>
                <td className="as-muted">{(m.trained_at || 'Not trained').slice(0, 10)}</td>
                <td>{m.deployment_status}</td>
                <td style={{
                  fontWeight: 600,
                  color: m.capability_status === 'VALIDATED' ? 'var(--sev-none)' : 'var(--muted)',
                }}>
                  {m.capability_status}
                </td>
                <td>
                  {typeof m.metrics === 'string'
                    ? <span className="as-muted">{m.metrics}</span>
                    : <code style={{ fontSize: 11 }}>{JSON.stringify(m.metrics)}</code>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

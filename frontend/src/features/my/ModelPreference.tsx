import { useModelSelect } from '../../components/Chat/ModelSelectContext';

export function ModelPreference() {
  const { modelId, modelOptions, setModelId } = useModelSelect();
  return <label className="setting-field">기본 AI 모델
    <select value={modelId} onChange={(e) => setModelId(e.target.value)}>
      {modelOptions.map((model) => <option key={model.id} value={model.id}>{model.label}</option>)}
    </select>
  </label>;
}

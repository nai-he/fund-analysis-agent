import { useState } from 'react'
import type { PositionInput, AnalyzeResult, UserFundItem, BatchFundResult, TabKey, SectionKey } from './types'
import { AnalyzeView } from './components/AnalyzeView'
import { PortfolioView } from './components/PortfolioView'
import { MarketDashboard } from './components/MarketDashboard'

export default function App() {
  const [mainTab, setMainTab] = useState<'analyze' | 'portfolio' | 'market'>('analyze')
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<AnalyzeResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<TabKey>('30d')
  const [activeSection, setActiveSection] = useState<SectionKey>('indicators')
  const [showRaw, setShowRaw] = useState(false)
  const [showPosition, setShowPosition] = useState(false)
  const [position, setPosition] = useState<PositionInput>({
    cost_nav: '', holding_amount: '', holding_units: '',
    is_dca: false, monthly_dca_amount: '',
    max_loss_percent: '15', holding_horizon: '1年以上', risk_preference: '平衡'
  })

  // 我的基金
  const [myFunds, setMyFunds] = useState<UserFundItem[]>([])
  const [myFundsLoading, setMyFundsLoading] = useState(false)
  const [batchResults, setBatchResults] = useState<BatchFundResult[]>([])
  const [batchLoading, setBatchLoading] = useState(false)
  const [newFundCode, setNewFundCode] = useState('')
  const [addFundError, setAddFundError] = useState('')
  const [editingFund, setEditingFund] = useState<UserFundItem | null>(null)
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' | 'info' } | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [editForm, setEditForm] = useState<{
    cost_nav: string; holding_amount: string; holding_units: string
    is_dca: boolean; monthly_dca_amount: string; max_loss_percent: string
    holding_horizon: string; risk_preference: string; note: string
  }>({
    cost_nav: '', holding_amount: '', holding_units: '',
    is_dca: false, monthly_dca_amount: '',
    max_loss_percent: '', holding_horizon: '', risk_preference: '', note: ''
  })

  const showToast = (message: string, type: 'success' | 'error' | 'info' = 'info') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 3000)
  }

  const handleAnalyze = async () => {
    const trimmed = code.trim()
    if (!trimmed) return
    if (!/^\d{5,6}$/.test(trimmed)) {
      setError('请输入5-6位数字基金代码')
      return
    }
    setLoading(true)
    setError(null)
    setResult(null)

    const hasPosition = showPosition && (position.cost_nav || position.holding_amount)

    try {
      let resp: Response
      if (hasPosition) {
        resp = await fetch('/api/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            code: trimmed,
            position: {
              cost_nav: position.cost_nav ? parseFloat(position.cost_nav) : undefined,
              holding_amount: position.holding_amount ? parseFloat(position.holding_amount) : undefined,
              holding_units: position.holding_units ? parseFloat(position.holding_units) : undefined,
              is_dca: position.is_dca,
              monthly_dca_amount: position.monthly_dca_amount ? parseFloat(position.monthly_dca_amount) : undefined,
              max_loss_percent: position.max_loss_percent ? parseFloat(position.max_loss_percent) : undefined,
              holding_horizon: position.holding_horizon || undefined,
              risk_preference: position.risk_preference || undefined,
            },
          }),
        })
      } else {
        resp = await fetch(`/api/analyze?code=${encodeURIComponent(trimmed)}`)
      }
      const data: AnalyzeResult = await resp.json()
      if (!resp.ok) {
        setError(data.error || `请求失败 (${resp.status})`)
      } else {
        setResult(data)
        if (!data.success) setError(data.error || '分析失败')
      }
    } catch (e) {
      setError(`网络请求失败：${e instanceof Error ? e.message : '未知错误'}。请确认后端服务已启动。`)
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleAnalyze()
  }

  // === 我的基金 handlers ===

  const loadMyFunds = async () => {
    setMyFundsLoading(true)
    try {
      const resp = await fetch('/api/my-funds')
      const data = await resp.json()
      setMyFunds(data.funds || [])
    } catch (e) {
      console.error('加载我的基金失败', e)
    } finally {
      setMyFundsLoading(false)
    }
  }

  const addFund = async () => {
    const trimmed = newFundCode.trim()
    if (!trimmed || !/^\d{5,6}$/.test(trimmed)) {
      setAddFundError('请输入5-6位数字基金代码')
      return
    }
    setAddFundError('')
    setMyFundsLoading(true)
    try {
      const resp = await fetch('/api/my-funds', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: trimmed }),
      })
      if (resp.ok) {
        setNewFundCode('')
        await loadMyFunds()
        showToast(`基金 ${trimmed} 已添加`, 'success')
      } else {
        const data = await resp.json().catch(() => ({}))
        setAddFundError(data.detail || `请求失败 (${resp.status})`)
      }
    } catch (e) {
      console.error('添加基金失败', e)
      setAddFundError('网络错误，请检查后端服务是否运行')
    } finally {
      setMyFundsLoading(false)
    }
  }

  const deleteFund = async (code: string) => {
    setMyFundsLoading(true)
    try {
      await fetch(`/api/my-funds/${code}`, { method: 'DELETE' })
      await loadMyFunds()
      setBatchResults(prev => prev.filter(r => r.code !== code))
      showToast(`基金 ${code} 已删除`, 'success')
    } catch (e) {
      console.error('删除基金失败', e)
      showToast('删除失败，请检查网络', 'error')
    } finally {
      setMyFundsLoading(false)
    }
  }

  const startEditFund = (fund: UserFundItem) => {
    setEditingFund(fund)
    setEditForm({
      cost_nav: fund.cost_nav != null ? String(fund.cost_nav) : '',
      holding_amount: fund.holding_amount != null ? String(fund.holding_amount) : '',
      holding_units: fund.holding_units != null ? String(fund.holding_units) : '',
      is_dca: fund.is_dca || false,
      monthly_dca_amount: fund.monthly_dca_amount != null ? String(fund.monthly_dca_amount) : '',
      max_loss_percent: fund.max_loss_percent != null ? String(fund.max_loss_percent) : '',
      holding_horizon: fund.holding_horizon || '',
      risk_preference: fund.risk_preference || '',
      note: fund.note || '',
    })
  }

  const saveEditFund = async () => {
    if (!editingFund) return
    const updated: UserFundItem = {
      code: editingFund.code,
      cost_nav: editForm.cost_nav ? parseFloat(editForm.cost_nav) : undefined,
      holding_amount: editForm.holding_amount ? parseFloat(editForm.holding_amount) : undefined,
      holding_units: editForm.holding_units ? parseFloat(editForm.holding_units) : undefined,
      is_dca: editForm.is_dca,
      monthly_dca_amount: editForm.monthly_dca_amount ? parseFloat(editForm.monthly_dca_amount) : undefined,
      max_loss_percent: editForm.max_loss_percent ? parseFloat(editForm.max_loss_percent) : undefined,
      holding_horizon: editForm.holding_horizon || undefined,
      risk_preference: editForm.risk_preference || undefined,
      note: editForm.note || undefined,
    }
    setMyFundsLoading(true)
    try {
      const resp = await fetch('/api/my-funds', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updated),
      })
      if (resp.ok) {
        setEditingFund(null)
        await loadMyFunds()
        showToast(`基金 ${editingFund.code} 已更新`, 'success')
      }
    } catch (e) {
      console.error('更新基金失败', e)
    } finally {
      setMyFundsLoading(false)
    }
  }

  const batchAnalyze = async () => {
    if (myFunds.length === 0) return
    setBatchLoading(true)
    setBatchResults([])
    try {
      const resp = await fetch('/api/my-funds/analyze', { method: 'POST' })
      const data = await resp.json()
      setBatchResults(data.results || [])
    } catch (e) {
      console.error('批量分析失败', e)
    } finally {
      setBatchLoading(false)
    }
  }

  return (
    <div className="app">
      <header className="header">
        <h1>基金决策辅助分析</h1>
        <p className="subtitle">个人研究参考工具 — 不构成投资建议</p>
        <nav className="main-tabs">
          <button className={`main-tab ${mainTab === 'analyze' ? 'active' : ''}`} onClick={() => setMainTab('analyze')}>单只分析</button>
          <button className={`main-tab ${mainTab === 'portfolio' ? 'active' : ''}`} onClick={() => { setMainTab('portfolio'); if (myFunds.length === 0) loadMyFunds(); }}>我的组合</button>
          <button className={`main-tab ${mainTab === 'market' ? 'active' : ''}`} onClick={() => setMainTab('market')}>宏观一览</button>
        </nav>
      </header>

      {/* === 单只分析 TAB === */}
      {mainTab === 'analyze' && (
        <AnalyzeView
          code={code} setCode={setCode}
          loading={loading} error={error} result={result}
          showPosition={showPosition} setShowPosition={setShowPosition}
          position={position} setPosition={setPosition}
          activeTab={activeTab} setActiveTab={setActiveTab}
          activeSection={activeSection} setActiveSection={setActiveSection}
          showRaw={showRaw} setShowRaw={setShowRaw}
          handleAnalyze={handleAnalyze} handleKeyDown={handleKeyDown}
        />
      )}

      {/* === 我的组合 TAB === */}
      {mainTab === 'portfolio' && (
        <PortfolioView
          myFunds={myFunds} myFundsLoading={myFundsLoading}
          batchResults={batchResults} batchLoading={batchLoading}
          newFundCode={newFundCode} setNewFundCode={setNewFundCode}
          addFundError={addFundError} setAddFundError={setAddFundError}
          editingFund={editingFund} setEditingFund={setEditingFund}
          editForm={editForm} setEditForm={setEditForm}
          confirmDelete={confirmDelete} setConfirmDelete={setConfirmDelete}
          addFund={addFund} loadMyFunds={loadMyFunds}
          startEditFund={startEditFund} saveEditFund={saveEditFund}
          deleteFund={deleteFund} batchAnalyze={batchAnalyze}
        />
      )}

      {/* === 宏观一览 TAB === */}
      {mainTab === 'market' && (
      <div className="tab-fade-in">
      <MarketDashboard />
      </div>
      )}

      {/* Toast 通知 */}
      {toast && (
        <div className={`toast toast-${toast.type}`}>
          <span className="toast-icon">{toast.type === 'success' ? '✓' : toast.type === 'error' ? '✕' : 'ℹ'}</span>
          <span className="toast-message">{toast.message}</span>
        </div>
      )}

      {/* 删除确认对话框 */}
      {confirmDelete && (
        <div className="dialog-overlay" onClick={() => setConfirmDelete(null)}>
          <div className="dialog-box" onClick={(e) => e.stopPropagation()}>
            <h3 className="dialog-title">确认删除</h3>
            <p className="dialog-text">确定要删除基金 {confirmDelete} 吗？此操作不可撤销。</p>
            <div className="dialog-actions">
              <button className="dialog-btn dialog-btn-cancel" onClick={() => setConfirmDelete(null)}>取消</button>
              <button className="dialog-btn dialog-btn-danger" onClick={() => { deleteFund(confirmDelete); setConfirmDelete(null); }}>确认删除</button>
            </div>
          </div>
        </div>
      )}

      <footer className="footer">
        <p>数据源：AKShare / efinance / Tencent | AI：Mindeck/My Codex API | 仅供个人研究参考，不构成投资建议</p>
      </footer>
    </div>
  )
}

import type { UserFundItem, BatchFundResult } from '../types'
import { EditField } from './common'
import { PortfolioSummaryCard, PortfolioWarningsCard, BatchResultCard, sortBatchResultsByPriority } from './PortfolioComponents'

interface PortfolioViewProps {
  myFunds: UserFundItem[]
  myFundsLoading: boolean
  batchResults: BatchFundResult[]
  batchLoading: boolean
  newFundCode: string
  setNewFundCode: (v: string) => void
  addFundError: string
  setAddFundError: (v: string) => void
  editingFund: UserFundItem | null
  setEditingFund: (f: UserFundItem | null) => void
  editForm: {
    cost_nav: string; holding_amount: string; holding_units: string
    is_dca: boolean; monthly_dca_amount: string; max_loss_percent: string
    holding_horizon: string; risk_preference: string; note: string
  }
  setEditForm: (f: PortfolioViewProps['editForm']) => void
  confirmDelete: string | null
  setConfirmDelete: (v: string | null) => void
  addFund: () => void
  loadMyFunds: () => void
  startEditFund: (fund: UserFundItem) => void
  saveEditFund: () => void
  deleteFund: (code: string) => void
  batchAnalyze: () => void
}

export function PortfolioView({
  myFunds, myFundsLoading, batchResults, batchLoading,
  newFundCode, setNewFundCode, addFundError, setAddFundError,
  editingFund, setEditingFund, editForm, setEditForm,
  confirmDelete, setConfirmDelete,
  addFund, loadMyFunds, startEditFund, saveEditFund, deleteFund, batchAnalyze,
}: PortfolioViewProps) {
  return (
    <div className="tab-fade-in">
    <div className="card">
      <div className="my-funds-header-row">
        <h3>我的基金（{myFunds.length}只）</h3>
        <button className="my-funds-refresh-btn" onClick={loadMyFunds} disabled={myFundsLoading}>
          {myFundsLoading ? '刷新中...' : '刷新'}
        </button>
      </div>

      {/* 添加基金 */}
      <div className="add-fund-row">
        <input
          type="text"
          className="add-fund-input"
          placeholder="输入5-6位基金代码"
          value={newFundCode}
          onChange={(e) => { setNewFundCode(e.target.value); setAddFundError(''); }}
          maxLength={6}
          onKeyDown={(e) => e.key === 'Enter' && addFund()}
        />
        <button className="add-fund-btn" onClick={addFund} disabled={myFundsLoading}>
          添加
        </button>
      </div>
      {addFundError && <p className="add-fund-error">{addFundError}</p>}

      {/* 基金列表 */}
      {myFunds.length === 0 ? (
        <p className="my-funds-empty">还没有添加基金，输入代码后点击"添加"</p>
      ) : (
        <div className="my-funds-list">
          {myFunds.map((fund) => (
            <div key={fund.code} className={`my-fund-row ${editingFund?.code === fund.code ? 'editing' : ''}`}>
              <div className="my-fund-row-main">
                <span className="my-fund-code">{fund.code}</span>
                <span className="my-fund-note">{fund.note || '未填写备注'}</span>
                <span className="my-fund-position-hint">
                  {fund.cost_nav != null ? `成本${fund.cost_nav}` : ''}
                  {fund.holding_amount != null ? ` 持有${fund.holding_amount}元` : ''}
                  {fund.is_dca ? ' 定投' : ''}
                </span>
                <div className="my-fund-row-actions">
                  <button
                    className={`my-fund-edit-btn ${editingFund?.code === fund.code ? 'editing-active' : ''}`}
                    onClick={() => editingFund?.code === fund.code ? setEditingFund(null) : startEditFund(fund)}
                  >
                    {editingFund?.code === fund.code ? '收起' : '编辑'}
                  </button>
                  <button className="my-fund-del-btn" onClick={() => setConfirmDelete(fund.code)}>删除</button>
                </div>
              </div>

              {/* 编辑表单 */}
              {editingFund?.code === fund.code && (
                <div className="my-fund-edit-form">
                  <div className="edit-form-grid">
                    <EditField label="持仓成本价" value={editForm.cost_nav} onChange={(v) => setEditForm({ ...editForm, cost_nav: v })} placeholder="如 0.75" />
                    <EditField label="持有金额（元）" value={editForm.holding_amount} onChange={(v) => setEditForm({ ...editForm, holding_amount: v })} placeholder="如 10000" />
                    <EditField label="持有份额（份）" value={editForm.holding_units} onChange={(v) => setEditForm({ ...editForm, holding_units: v })} placeholder="如 13000" />
                    <EditField label="每月定投金额" value={editForm.monthly_dca_amount} onChange={(v) => setEditForm({ ...editForm, monthly_dca_amount: v })} placeholder="如 1000" />
                    <EditField label="最大可承受亏损%" value={editForm.max_loss_percent} onChange={(v) => setEditForm({ ...editForm, max_loss_percent: v })} placeholder="如 15" />
                    <div className="form-group">
                      <label className="form-label">是否定投</label>
                      <label className="checkbox-label">
                        <input type="checkbox" checked={editForm.is_dca} onChange={(e) => setEditForm({ ...editForm, is_dca: e.target.checked })} />
                        是，我正在进行定投
                      </label>
                    </div>
                    <div className="form-group">
                      <label className="form-label">计划持有周期</label>
                      <select className="edit-form-select" value={editForm.holding_horizon} onChange={(e) => setEditForm({ ...editForm, holding_horizon: e.target.value })}>
                        <option value="">不填写</option>
                        <option value="短期">短期</option>
                        <option value="3-6个月">3-6个月</option>
                        <option value="1年以上">1年以上</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label className="form-label">操作偏好</label>
                      <select className="edit-form-select" value={editForm.risk_preference} onChange={(e) => setEditForm({ ...editForm, risk_preference: e.target.value })}>
                        <option value="">不填写</option>
                        <option value="保守">保守</option>
                        <option value="平衡">平衡</option>
                        <option value="激进">激进</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label className="form-label">备注</label>
                      <input type="text" className="edit-form-input" value={editForm.note} onChange={(e) => setEditForm({ ...editForm, note: e.target.value })} placeholder="如 白酒LOF定投" />
                    </div>
                  </div>
                  <div className="edit-form-actions">
                    <button className="edit-form-save-btn" onClick={saveEditFund}>保存</button>
                    <button className="edit-form-cancel-btn" onClick={() => setEditingFund(null)}>取消</button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* 批量分析 */}
      {myFunds.length > 0 && (
        <>
          <div className="batch-analyze-row">
            <button className="batch-analyze-btn" onClick={batchAnalyze} disabled={batchLoading}>
              {batchLoading ? '正在批量分析...' : '一键分析全部基金'}
            </button>
          </div>

          {batchResults.length > 0 && (
            <div className="batch-results">
              <PortfolioSummaryCard batchResults={batchResults} myFunds={myFunds} />
              <PortfolioWarningsCard batchResults={batchResults} myFunds={myFunds} />
              <h4 className="batch-results-title">逐只分析结果</h4>
              {sortBatchResultsByPriority(batchResults).map((r) => (
                <BatchResultCard key={r.code} result={r} fundItem={myFunds.find(f => f.code === r.code)} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
    </div>
  )
}

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  RefreshControl,
  TextInput,
  Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import Slider from '@react-native-community/slider';
import { InfoButton, GlossaryScreen } from './FinanceTooltip';

const API_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface Position {
  rank: number;
  symbol: string;
  name: string;
  score: number;
  confidence: number;
  allocation_pct: number;
  amount_inr: number;
  current_price: number;
  change_24h: number;
  quantity: number;
  entry: { price: number; range_low: number; range_high: number; instruction: string };
  stop_loss: { price: number; pct: number; loss_inr: number; based_on: string };
  take_profit: {
    tp1: { price: number; pct: number; action: string; gross_gain: number; after_tax: number };
    tp2: { price: number; pct: number; action: string; gross_gain: number; after_tax: number };
    tp3: { price: number; pct: number; action: string; gross_gain: number };
  };
  expected_outcome: { best_case_inr: number; expected_inr: number; worst_case_inr: number; win_probability: number; note: string };
  exit_instructions: Array<{ step: number | string; condition: string; action: string; detail: string }>;
  reasoning_summary: string;
}

interface TradePlan {
  verdict: string;
  verdict_reason: string;
  date: string;
  time_ist: string;
  budget: number;
  risk_profile: string;
  summary: { total_deployed: number; deployment_pct: number; positions_count: number; best_case_total: number; expected_total: number; worst_case_total: number; worst_case_note?: string; tax_note?: string };
  positions: Position[];
  alternatives?: Array<{ action: string; detail: string }>;
  market_summary?: { mood: string; mood_detail: string; btc_price: number; btc_change: number; eth_price: number; eth_change: number };
  all_scores?: Array<{ symbol: string; name: string; score: number; action: string; change_24h: number }>;
}

const RISK_PROFILES = [
  { key: 'conservative', label: 'Safe', icon: 'shield-checkmark' as const },
  { key: 'moderate', label: 'Balanced', icon: 'scale' as const },
  { key: 'aggressive', label: 'Bold', icon: 'flame' as const },
];

const VERDICT_CONFIG: Record<string, { color: string; bg: string; icon: string }> = {
  YES: { color: '#10b981', bg: 'rgba(16, 185, 129, 0.15)', icon: 'checkmark-circle' },
  NO: { color: '#ef4444', bg: 'rgba(239, 68, 68, 0.15)', icon: 'close-circle' },
  WAIT: { color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.15)', icon: 'time' },
};

export default function DecisionScreen() {
  const [plan, setPlan] = useState<TradePlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [budget, setBudget] = useState(10000);
  const [budgetInput, setBudgetInput] = useState('10000');
  const [riskProfile, setRiskProfile] = useState('moderate');
  const [expandedPosition, setExpandedPosition] = useState<string | null>(null);
  const [showAllScores, setShowAllScores] = useState(false);
  const [showGlossary, setShowGlossary] = useState(false);
  const [assetMode, setAssetMode] = useState<'crypto' | 'stocks'>('crypto');

  useEffect(() => { fetchPlan(); }, []);

  const fetchPlan = useCallback(async (b?: number, r?: string, mode?: string) => {
    try {
      setLoading(true);
      const useBudget = b ?? budget;
      const useRisk = r ?? riskProfile;
      const useMode = mode ?? assetMode;
      const endpoint = useMode === 'stocks' 
        ? `${API_URL}/api/stocks/trade-plan?budget=${useBudget}&risk_profile=${useRisk}&max_stocks=5`
        : `${API_URL}/api/scoring/trade-plan?budget=${useBudget}&risk_profile=${useRisk}&max_coins=5`;
      const response = await fetch(endpoint);
      const data = await response.json();
      setPlan(data);
    } catch (error) {
      console.error('Error fetching trade plan:', error);
    } finally {
      setLoading(false);
    }
  }, [budget, riskProfile, assetMode]);

  const onRefresh = async () => { setRefreshing(true); await fetchPlan(); setRefreshing(false); };

  const handleBudgetSubmit = () => {
    const val = parseFloat(budgetInput) || 10000;
    const clamped = Math.max(500, Math.min(5000000, val));
    setBudget(clamped);
    setBudgetInput(String(clamped));
    fetchPlan(clamped);
  };

  const handleSliderChange = (val: number) => {
    const rounded = Math.round(val / 500) * 500;
    setBudget(rounded);
    setBudgetInput(String(rounded));
  };

  const handleSliderComplete = (val: number) => {
    const rounded = Math.round(val / 500) * 500;
    fetchPlan(rounded);
  };

  const handleRiskChange = (profile: string) => { setRiskProfile(profile); fetchPlan(budget, profile); };

  const handleAssetModeChange = (mode: 'crypto' | 'stocks') => {
    setAssetMode(mode);
    setExpandedPosition(null);
    setShowAllScores(false);
    fetchPlan(budget, riskProfile, mode);
  };

  const fmt = (v: number | undefined | null) => {
    const safe = v ?? 0;
    if (Math.abs(safe) >= 100000) return `Rs ${(safe / 100000).toFixed(2)}L`;
    return `Rs ${safe.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
  };

  if (loading && !plan) {
    return (
      <SafeAreaView style={st.container} edges={['top']}>
        <View style={st.loadingWrap}>
          <ActivityIndicator size="large" color="#f59e0b" />
          <Text style={st.loadingText}>{assetMode === 'stocks' ? 'Analyzing 50 stocks across 5 factors...' : 'Analyzing 20 coins across 4 factors...'}</Text>
        </View>
      </SafeAreaView>
    );
  }

  const verdict = plan?.verdict || 'WAIT';
  const vc = VERDICT_CONFIG[verdict] || VERDICT_CONFIG.WAIT;

  return (
    <SafeAreaView style={st.container} edges={['top']}>
      <GlossaryScreen visible={showGlossary} onClose={() => setShowGlossary(false)} />
      <ScrollView style={st.scroll} contentContainerStyle={st.content} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#f59e0b" />}>

        {/* Header */}
        <View style={st.header}>
          <View>
            <Text style={st.headerTitle}>Today's plan</Text>
            <Text style={st.headerSub}>{plan?.date} {plan?.time_ist}</Text>
          </View>
          <TouchableOpacity style={st.learnBtn} onPress={() => setShowGlossary(true)}>
            <Ionicons name="book-outline" size={16} color="#f59e0b" />
            <Text style={st.learnBtnText}>Learn</Text>
          </TouchableOpacity>
        </View>

        {/* Asset Mode Tabs */}
        <View style={st.tabRow}>
          <TouchableOpacity style={[st.tab, assetMode === 'crypto' && st.tabActive]} onPress={() => handleAssetModeChange('crypto')}>
            <Ionicons name="logo-bitcoin" size={16} color={assetMode === 'crypto' ? '#f59e0b' : '#6b7280'} />
            <Text style={[st.tabText, assetMode === 'crypto' && st.tabTextActive]}>Crypto</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[st.tab, assetMode === 'stocks' && st.tabActive]} onPress={() => handleAssetModeChange('stocks')}>
            <Ionicons name="trending-up" size={16} color={assetMode === 'stocks' ? '#3b82f6' : '#6b7280'} />
            <Text style={[st.tabText, assetMode === 'stocks' && st.tabTextActive]}>Stocks</Text>
          </TouchableOpacity>
        </View>

        {/* VERDICT */}
        <View style={[st.verdictCard, { borderColor: vc.color }]}>
          <View style={[st.verdictBadge, { backgroundColor: vc.bg }]}>
            <Ionicons name={vc.icon as any} size={48} color={vc.color} />
          </View>
          <Text style={[st.verdictText, { color: vc.color }]}>
            {verdict === 'YES' ? 'TRADE TODAY' : verdict === 'NO' ? 'DO NOT TRADE' : 'WAIT'}
          </Text>
          <Text style={st.verdictReason}>{plan?.verdict_reason}</Text>
          {verdict === 'YES' && plan?.summary && (
            <View style={st.verdictSummary}>
              <View style={st.verdictMetric}><Text style={st.vmLabel}>Deploying</Text><Text style={[st.vmVal, { color: '#10b981' }]}>{fmt(plan.summary.total_deployed)}</Text></View>
              <View style={st.verdictMetric}><Text style={st.vmLabel}>Positions</Text><Text style={st.vmVal}>{plan.summary.positions_count}</Text></View>
              <View style={st.verdictMetric}><Text style={st.vmLabel}>Best case</Text><Text style={[st.vmVal, { color: '#10b981' }]}>+{fmt(plan.summary.best_case_total)}</Text></View>
              <View style={st.verdictMetric}><Text style={st.vmLabel}>Worst case</Text><Text style={[st.vmVal, { color: '#ef4444' }]}>{fmt(plan.summary.worst_case_total)}</Text></View>
            </View>
          )}
        </View>

        {/* BUDGET + RISK */}
        <View style={st.ctrlCard}>
          <Text style={st.ctrlLabel}>Your budget</Text>
          <View style={st.budgetRow}>
            <Text style={st.rupee}>Rs</Text>
            <TextInput style={st.budgetInput} value={budgetInput} onChangeText={setBudgetInput} onSubmitEditing={handleBudgetSubmit} keyboardType="numeric" returnKeyType="go" />
            <TouchableOpacity style={st.goBtn} onPress={handleBudgetSubmit}><Text style={st.goBtnText}>Update</Text></TouchableOpacity>
          </View>
          <Slider style={st.slider} minimumValue={1000} maximumValue={500000} step={500} value={budget} onValueChange={handleSliderChange} onSlidingComplete={handleSliderComplete} minimumTrackTintColor="#f59e0b" maximumTrackTintColor="#2d2d44" thumbTintColor="#f59e0b" />
          <View style={st.sliderLabels}><Text style={st.sliderLbl}>Rs 1K</Text><Text style={st.sliderVal}>{fmt(budget)}</Text><Text style={st.sliderLbl}>Rs 5L</Text></View>
          <Text style={[st.ctrlLabel, { marginTop: 16 }]}>Risk tolerance</Text>
          <View style={st.riskRow}>
            {RISK_PROFILES.map((p) => (
              <TouchableOpacity key={p.key} style={[st.riskChip, riskProfile === p.key && st.riskActive]} onPress={() => handleRiskChange(p.key)}>
                <Ionicons name={p.icon} size={14} color={riskProfile === p.key ? '#f59e0b' : '#6b7280'} />
                <Text style={[st.riskText, riskProfile === p.key && st.riskTextActive]}>{p.label}</Text>
              </TouchableOpacity>
            ))}
            <InfoButton termKey="confidence_score" size={14} />
          </View>
        </View>

        {/* POSITIONS */}
        {plan?.positions && plan.positions.length > 0 && (
          <View style={st.posSection}>
            <Text style={st.secTitle}>Your trade plan</Text>
            <Text style={st.secSub}>Tap a coin for entry/exit details</Text>
            {plan.positions.map((pos) => {
              const isExp = expandedPosition === pos.symbol;
              return (
                <TouchableOpacity key={pos.symbol} style={st.posCard} onPress={() => setExpandedPosition(isExp ? null : pos.symbol)} activeOpacity={0.85}>
                  <View style={st.posHead}>
                    <View style={st.posRank}><Text style={st.posRankT}>#{pos.rank}</Text></View>
                    <View style={{ flex: 1 }}><Text style={st.posSymbol}>{pos.symbol}</Text><Text style={st.posName}>{pos.name}</Text></View>
                    <View style={st.posRight}><Text style={st.posAmt}>{fmt(pos.amount_inr)}</Text><Text style={st.posAlloc}>{pos.allocation_pct}% of budget</Text></View>
                  </View>
                  <View style={st.posStats}>
                    <View style={st.posSt}><Text style={st.posStL}>Entry</Text><Text style={st.posStV}>{fmt(pos.entry.price)}</Text></View>
                    <View style={st.posSt}><Text style={st.posStL}>Stop loss</Text><Text style={[st.posStV, { color: '#ef4444' }]}>{fmt(pos.stop_loss.price)}</Text></View>
                    <View style={st.posSt}><Text style={st.posStL}>Target</Text><Text style={[st.posStV, { color: '#10b981' }]}>{fmt(pos.take_profit.tp1.price)}</Text></View>
                    <View style={st.posSt}><Text style={st.posStL}>Win prob</Text><Text style={st.posStV}>{pos.expected_outcome.win_probability}%</Text></View>
                  </View>
                  <View style={st.outBar}>
                    <Text style={[st.outVal, { color: '#ef4444' }]}>{fmt(pos.expected_outcome.worst_case_inr)}</Text>
                    <View style={st.outTrack}><View style={[st.outFill, { width: `${Math.min(pos.expected_outcome.win_probability, 100)}%` }]} /></View>
                    <Text style={[st.outVal, { color: '#10b981' }]}>+{fmt(pos.expected_outcome.best_case_inr)}</Text>
                  </View>
                  {isExp && (
                    <View style={st.expSection}>
                      <View style={st.instrSec}><Text style={st.instrTitle}>How to enter</Text><Text style={st.instrBody}>{pos.entry.instruction}</Text><Text style={st.instrDet}>Quantity: {pos.quantity.toFixed(6)} {pos.symbol}</Text></View>
                      <View style={st.instrSec}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}><Text style={st.instrTitle}>Exit plan (follow in order)</Text><InfoButton termKey="take_profit" size={13} /></View>
                        {pos.exit_instructions.map((step, i) => {
                          const isSL = step.step === 'STOP LOSS';
                          return (
                            <View key={i} style={[st.exitStep, isSL && st.exitDanger]}>
                              <View style={[st.exitBadge, isSL && { backgroundColor: 'rgba(239,68,68,0.2)' }]}><Text style={[st.exitNum, isSL && { color: '#ef4444' }]}>{isSL ? 'SL' : step.step}</Text></View>
                              <View style={{ flex: 1 }}>
                                <Text style={[st.exitCond, isSL && { color: '#ef4444' }]}>{step.condition}</Text>
                                <Text style={st.exitAct}>{step.action}</Text>
                                <Text style={st.exitDet}>{step.detail}</Text>
                              </View>
                            </View>
                          );
                        })}
                      </View>
                      <View style={st.taxNote}><Ionicons name="receipt-outline" size={14} color="#f59e0b" /><Text style={st.taxNoteT}>{assetMode === 'stocks' ? `After 15% STCG tax: TP1 nets ${fmt(pos.take_profit.tp1.after_tax)}, TP2 nets ${fmt(pos.take_profit.tp2.after_tax)}.` : `After 30% VDA tax: TP1 nets ${fmt(pos.take_profit.tp1.after_tax)}, TP2 nets ${fmt(pos.take_profit.tp2.after_tax)}. Loss of ${fmt(pos.stop_loss.loss_inr)} cannot be offset.`}</Text></View>
                      <Text style={st.reasoning}>{pos.reasoning_summary}</Text>
                    </View>
                  )}
                  <View style={st.expInd}><Ionicons name={isExp ? 'chevron-up' : 'chevron-down'} size={18} color="#6b7280" /></View>
                </TouchableOpacity>
              );
            })}
            {plan.summary.tax_note && (<View style={st.taxBanner}><Ionicons name="warning" size={14} color="#f59e0b" /><Text style={st.taxBannerT}>{plan.summary.tax_note}</Text></View>)}
          </View>
        )}

        {/* ALTERNATIVES (NO/WAIT) */}
        {plan?.alternatives && plan.alternatives.length > 0 && (
          <View style={st.altSec}>
            <Text style={st.secTitle}>What to do instead</Text>
            {plan.alternatives.map((alt, i) => (<View key={i} style={st.altCard}><Text style={st.altAct}>{alt.action}</Text><Text style={st.altDet}>{alt.detail}</Text></View>))}
          </View>
        )}

        {/* MARKET */}
        {plan?.market_summary && (
          <View style={st.mktSec}>
            <Text style={st.secTitle}>Market snapshot</Text>
            <View style={st.mktRow}>
              {assetMode === 'crypto' && plan.market_summary.btc_price ? (
                <>
                  <View style={st.mktCard}><Text style={st.mktLbl}>BTC</Text><Text style={st.mktPrice}>{fmt(plan.market_summary.btc_price)}</Text><Text style={[st.mktChg, { color: (plan.market_summary.btc_change ?? 0) >= 0 ? '#10b981' : '#ef4444' }]}>{(plan.market_summary.btc_change ?? 0) >= 0 ? '+' : ''}{plan.market_summary.btc_change?.toFixed(1)}%</Text></View>
                  <View style={st.mktCard}><Text style={st.mktLbl}>ETH</Text><Text style={st.mktPrice}>{fmt(plan.market_summary.eth_price)}</Text><Text style={[st.mktChg, { color: (plan.market_summary.eth_change ?? 0) >= 0 ? '#10b981' : '#ef4444' }]}>{(plan.market_summary.eth_change ?? 0) >= 0 ? '+' : ''}{plan.market_summary.eth_change?.toFixed(1)}%</Text></View>
                </>
              ) : null}
              <View style={st.mktCard}><Text style={st.mktLbl}>Mood</Text><Text style={st.mktMood}>{plan.market_summary.mood}</Text><Text style={st.mktMoodDet} numberOfLines={2}>{plan.market_summary.mood_detail}</Text></View>
            </View>
          </View>
        )}

        {/* ALL SCORES */}
        {plan?.all_scores && plan.all_scores.length > 0 && (
          <View style={st.allSec}>
            <TouchableOpacity style={st.allHead} onPress={() => setShowAllScores(!showAllScores)}>
              <Text style={st.secTitle}>{assetMode === 'stocks' ? 'All stock scores' : 'All coin scores'} ({plan.all_scores.length})</Text>
              <Ionicons name={showAllScores ? 'chevron-up' : 'chevron-down'} size={18} color="#6b7280" />
            </TouchableOpacity>
            {showAllScores && plan.all_scores.map((c: any) => {
              const ac = c.action === 'BUY' ? '#10b981' : c.action === 'SELL' ? '#ef4444' : '#f59e0b';
              return (<View key={c.symbol} style={st.scRow}><View style={{flex:1}}><Text style={st.scSym}>{c.symbol}</Text>{c.sector ? <Text style={{color:'#6b7280',fontSize:10}}>{c.sector}</Text> : null}</View><View style={[st.scBadge, { backgroundColor: ac + '20' }]}><Text style={[st.scBadgeT, { color: ac }]}>{c.action}</Text></View><Text style={st.scVal}>{c.score >= 0 ? '+' : ''}{c.score.toFixed(1)}</Text><Text style={[st.scChg, { color: c.change_24h >= 0 ? '#10b981' : '#ef4444' }]}>{c.change_24h >= 0 ? '+' : ''}{c.change_24h.toFixed(1)}%</Text></View>);
            })}
          </View>
        )}

        {/* DISCLAIMER */}
        <View style={st.disc}><Ionicons name="alert-circle" size={16} color="#ef4444" /><Text style={st.discT}>{assetMode === 'stocks' ? 'NOT financial advice. Past performance does not guarantee future results. STCG taxed at 15% for holdings under 1 year. Consult a SEBI-registered advisor. Educational use only.' : 'NOT financial advice. Past performance does not guarantee future results. Crypto taxed at 30% (VDA) + 1% TDS in India. Educational use only. Never invest money you cannot afford to lose.'}</Text></View>
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f0f23' },
  loadingWrap: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  loadingText: { color: '#9ca3af', marginTop: 12, fontSize: 14 },
  scroll: { flex: 1 }, content: { padding: 20, paddingBottom: 40 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 16 },
  headerTitle: { fontSize: 26, fontWeight: '700', color: '#fff' },
  headerSub: { fontSize: 13, color: '#6b7280', marginTop: 2 },
  learnBtn: { flexDirection: 'row', alignItems: 'center', backgroundColor: 'rgba(245,158,11,0.1)', paddingHorizontal: 12, paddingVertical: 7, borderRadius: 16, borderWidth: 1, borderColor: 'rgba(245,158,11,0.2)', gap: 4 },
  learnBtnText: { color: '#f59e0b', fontSize: 12, fontWeight: '600' },
  verdictCard: { backgroundColor: '#1a1a2e', borderRadius: 20, padding: 24, borderWidth: 2, alignItems: 'center', marginBottom: 16 },
  verdictBadge: { width: 80, height: 80, borderRadius: 40, justifyContent: 'center', alignItems: 'center', marginBottom: 12 },
  verdictText: { fontSize: 28, fontWeight: '800', marginBottom: 10 },
  verdictReason: { color: '#9ca3af', fontSize: 13, textAlign: 'center', lineHeight: 20 },
  verdictSummary: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', marginTop: 16, gap: 12 },
  verdictMetric: { alignItems: 'center', minWidth: 70 },
  vmLabel: { color: '#6b7280', fontSize: 11 }, vmVal: { color: '#fff', fontSize: 16, fontWeight: '700', marginTop: 2 },
  ctrlCard: { backgroundColor: '#1a1a2e', borderRadius: 16, padding: 16, marginBottom: 16 },
  ctrlLabel: { color: '#9ca3af', fontSize: 12, fontWeight: '600', marginBottom: 8 },
  budgetRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  rupee: { color: '#f59e0b', fontSize: 18, fontWeight: '700' },
  budgetInput: { flex: 1, backgroundColor: '#0f0f23', borderRadius: 10, paddingHorizontal: 14, paddingVertical: 10, color: '#fff', fontSize: 18, fontWeight: '600' },
  goBtn: { backgroundColor: '#f59e0b', paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10 },
  goBtnText: { color: '#000', fontSize: 13, fontWeight: '700' },
  slider: { width: '100%', height: 36, marginTop: 4 },
  sliderLabels: { flexDirection: 'row', justifyContent: 'space-between', marginTop: -4 },
  sliderLbl: { color: '#6b7280', fontSize: 11 }, sliderVal: { color: '#f59e0b', fontSize: 12, fontWeight: '600' },
  riskRow: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  riskChip: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: '#0f0f23', paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20 },
  riskActive: { backgroundColor: 'rgba(245,158,11,0.15)', borderWidth: 1, borderColor: 'rgba(245,158,11,0.3)' },
  riskText: { color: '#6b7280', fontSize: 13, fontWeight: '500' }, riskTextActive: { color: '#f59e0b' },
  posSection: { marginBottom: 16 },
  secTitle: { color: '#fff', fontSize: 17, fontWeight: '600', marginBottom: 4 },
  secSub: { color: '#6b7280', fontSize: 12, marginBottom: 12 },
  posCard: { backgroundColor: '#1a1a2e', borderRadius: 14, padding: 16, marginBottom: 10, borderWidth: 1, borderColor: '#2d2d44' },
  posHead: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  posRank: { width: 28, height: 28, borderRadius: 14, backgroundColor: 'rgba(245,158,11,0.15)', justifyContent: 'center', alignItems: 'center' },
  posRankT: { color: '#f59e0b', fontSize: 12, fontWeight: '700' },
  posSymbol: { color: '#fff', fontSize: 16, fontWeight: '600' }, posName: { color: '#6b7280', fontSize: 11 },
  posRight: { alignItems: 'flex-end' }, posAmt: { color: '#10b981', fontSize: 15, fontWeight: '600' }, posAlloc: { color: '#6b7280', fontSize: 11 },
  posStats: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 14, paddingTop: 12, borderTopWidth: 1, borderTopColor: '#2d2d44' },
  posSt: { alignItems: 'center' }, posStL: { color: '#6b7280', fontSize: 10 }, posStV: { color: '#fff', fontSize: 13, fontWeight: '600', marginTop: 2 },
  outBar: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 12 },
  outVal: { fontSize: 11, fontWeight: '600', minWidth: 50 },
  outTrack: { flex: 1, height: 6, backgroundColor: '#ef444430', borderRadius: 3, overflow: 'hidden' },
  outFill: { height: '100%', borderRadius: 3, backgroundColor: '#10b981' },
  expSection: { marginTop: 14, paddingTop: 14, borderTopWidth: 1, borderTopColor: '#2d2d44' },
  instrSec: { marginBottom: 14 }, instrTitle: { color: '#f59e0b', fontSize: 12, fontWeight: '600', marginBottom: 6 },
  instrBody: { color: '#d1d5db', fontSize: 12, lineHeight: 18 }, instrDet: { color: '#6b7280', fontSize: 11, marginTop: 4 },
  exitStep: { flexDirection: 'row', gap: 10, marginBottom: 10, paddingBottom: 10, borderBottomWidth: 0.5, borderBottomColor: '#2d2d44' },
  exitDanger: { backgroundColor: 'rgba(239,68,68,0.05)', borderRadius: 8, padding: 10, marginHorizontal: -4, borderBottomWidth: 0 },
  exitBadge: { width: 28, height: 28, borderRadius: 14, backgroundColor: 'rgba(245,158,11,0.15)', justifyContent: 'center', alignItems: 'center', marginTop: 2 },
  exitNum: { color: '#f59e0b', fontSize: 11, fontWeight: '700' },
  exitCond: { color: '#fff', fontSize: 12, fontWeight: '600' }, exitAct: { color: '#10b981', fontSize: 12, fontWeight: '600', marginTop: 2 },
  exitDet: { color: '#9ca3af', fontSize: 11, lineHeight: 16, marginTop: 3 },
  taxNote: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, backgroundColor: 'rgba(245,158,11,0.08)', borderRadius: 10, padding: 12, marginBottom: 10 },
  taxNoteT: { color: '#f59e0b', fontSize: 11, lineHeight: 16, flex: 1 },
  reasoning: { color: '#6b7280', fontSize: 11, lineHeight: 16, fontStyle: 'italic' },
  expInd: { alignItems: 'center', marginTop: 6 },
  altSec: { marginBottom: 16 }, altCard: { backgroundColor: '#1a1a2e', borderRadius: 12, padding: 14, marginBottom: 8 },
  altAct: { color: '#f59e0b', fontSize: 14, fontWeight: '600' }, altDet: { color: '#9ca3af', fontSize: 12, marginTop: 4, lineHeight: 18 },
  mktSec: { marginBottom: 16 }, mktRow: { flexDirection: 'row', gap: 8 },
  mktCard: { flex: 1, backgroundColor: '#1a1a2e', borderRadius: 12, padding: 12, alignItems: 'center' },
  mktLbl: { color: '#6b7280', fontSize: 11, fontWeight: '600' }, mktPrice: { color: '#fff', fontSize: 14, fontWeight: '600', marginTop: 4 },
  mktChg: { fontSize: 12, fontWeight: '600', marginTop: 2 }, mktMood: { color: '#fff', fontSize: 14, fontWeight: '600', marginTop: 4 },
  mktMoodDet: { color: '#6b7280', fontSize: 10, textAlign: 'center', marginTop: 2 },
  allSec: { marginBottom: 16 }, allHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  scRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 6, borderBottomWidth: 0.5, borderBottomColor: '#2d2d44', gap: 10 },
  scSym: { color: '#fff', fontSize: 13, fontWeight: '600', width: 50 },
  scBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4, minWidth: 42, alignItems: 'center' },
  scBadgeT: { fontSize: 10, fontWeight: '700' }, scVal: { color: '#d1d5db', fontSize: 12, flex: 1, textAlign: 'right' },
  scChg: { fontSize: 12, fontWeight: '500', width: 50, textAlign: 'right' },
  taxBanner: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, backgroundColor: 'rgba(245,158,11,0.08)', borderRadius: 10, padding: 12, marginTop: 4 },
  taxBannerT: { color: '#f59e0b', fontSize: 11, lineHeight: 16, flex: 1 },
  disc: { flexDirection: 'row', alignItems: 'flex-start', gap: 10, backgroundColor: 'rgba(239,68,68,0.08)', borderRadius: 12, padding: 14, marginTop: 8 },
  discT: { color: '#ef4444', fontSize: 11, lineHeight: 16, flex: 1 },
  tabRow: { flexDirection: 'row', gap: 8, marginBottom: 14 },
  tab: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12, borderRadius: 12, backgroundColor: '#1a1a2e', borderWidth: 1, borderColor: '#2d2d44' },
  tabActive: { borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.1)' },
  tabText: { color: '#6b7280', fontSize: 14, fontWeight: '600' },
  tabTextActive: { color: '#f59e0b' },
});
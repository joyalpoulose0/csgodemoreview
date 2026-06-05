/*
Main parser file using Go, many of the functions and analytics has been completed using demoinfocs-golang.
For reference:
*/

package main

import (
	"encoding/json"
	"fmt"
	"log"
	"math"
	"os"
	"sort"

	"github.com/golang/geo/r3"
	dem "github.com/markus-wa/demoinfocs-golang/v5/pkg/demoinfocs"
	common "github.com/markus-wa/demoinfocs-golang/v5/pkg/demoinfocs/common"
	events "github.com/markus-wa/demoinfocs-golang/v5/pkg/demoinfocs/events"
)

type Vec3 struct {
	X float32 `json:"x"`
	Y float32 `json:"y"`
	Z float32 `json:"z"`
}

// Killevent and its details
type KillEvent struct {
	Tick          int    `json:"tick"`
	Round         int    `json:"round"`
	KillerName    string `json:"killer_name"`
	KillerSteamID uint64 `json:"killer_steam_id"`
	KillerSide    string `json:"killer_side"`
	KillerTeam    string `json:"killer_team"`
	VictimTeam    string `json:"victim_team"`
	VictimName    string `json:"victim_name"`
	VictimSteamID uint64 `json:"victim_steam_id"`
	VictimSide    string `json:"victim_side"`
	Weapon        string `json:"weapon"`
	Headshot      bool   `json:"headshot"`
	Wallbang      bool   `json:"wallbang"`
	NoScope       bool   `json:"noscope"`
	ThroughSmoke  bool   `json:"through_smoke"`
	AttackerBlind bool   `json:"attacker_blind"`
	IsEntry       bool   `json:"is_entry"`
	IsTrade       bool   `json:"is_trade"`
	KillerPos     Vec3   `json:"killer_pos"`
	VictimPos     Vec3   `json:"victim_pos"`
}

type DamageEvent struct {
	Tick            int    `json:"tick"`
	Round           int    `json:"round"`
	AttackerName    string `json:"attacker_name"`
	AttackerSteamID uint64 `json:"attacker_steam_id"`
	VictimName      string `json:"victim_name"`
	Weapon          string `json:"weapon"`
	HealthDamage    int    `json:"health_damage"`
	ArmorDamage     int    `json:"armor_damage"`
	HitGroup        string `json:"hit_group"`
}

type FlashEvent struct {
	Tick           int     `json:"tick"`
	Round          int     `json:"round"`
	ThrowerName    string  `json:"thrower_name"`
	ThrowerSteamID uint64  `json:"thrower_steam_id"`
	ThrowerSide    string  `json:"thrower_side"`
	FlashedName    string  `json:"flashed_name"`
	FlashedSide    string  `json:"flashed_side"`
	Duration       float32 `json:"duration_seconds"`
	IsTeamFlash    bool    `json:"is_team_flash"`
}

type GrenadeEvent struct {
	Tick           int    `json:"tick"`
	Round          int    `json:"round"`
	ThrowerName    string `json:"thrower_name"`
	ThrowerSteamID uint64 `json:"thrower_steam_id"`
	ThrowerSide    string `json:"thrower_side"`
	GrenadeType    string `json:"grenade_type"`
	Position       Vec3   `json:"position"`
}

type BombEvent struct {
	Tick       int    `json:"tick"`
	Round      int    `json:"round"`
	EventType  string `json:"event_type"` // Plant event
	PlayerName string `json:"player_name"`
	Site       string `json:"site"`
}

type RoundEvent struct {
	Round        int    `json:"round"`
	StartTick    int    `json:"start_tick"`
	EndTick      int    `json:"end_tick"`
	Winner       string `json:"winner"`
	WinReason    string `json:"win_reason"`
	Duration     int    `json:"duration_ticks"`
	CTEquipValue int    `json:"ct_equip_value"` // for further analysis of round economy
	TEquipValue  int    `json:"t_equip_value"`
}

type PlayerRoundStats struct {
	SteamID        uint64 `json:"steam_id"`
	Name           string `json:"name"`
	Side           string `json:"side"`
	Kills          int    `json:"kills"`
	Deaths         int    `json:"deaths"`
	Assists        int    `json:"assists"`
	Headshots      int    `json:"headshots"`
	DamageDealt    int    `json:"damage_dealt"`
	FlashAssists   int    `json:"flash_assists"`
	GrenadesThrown int    `json:"grenades_thrown"`
	TradeKills     int    `json:"trade_kills"`
	EntryKill      bool   `json:"entry_kill"`
	EntryDeath     bool   `json:"entry_death"`
	Round          int    `json:"round"`
	TradedDeath    bool   `json:"traded_death"`
	OpeningDuel    bool   `json:"opening_duel"`
	Survived       bool   `json:"survived"`
}

type PlayerPositionSample struct {
	Tick    int    `json:"tick"`
	Round   int    `json:"round"`
	SteamID uint64 `json:"steam_id"`
	Name    string `json:"name"`
	Pos     Vec3   `json:"pos"`
	IsAlive bool   `json:"is_alive"`
}

type PlayerSummary struct {
	SteamID        uint64  `json:"steam_id"`
	Name           string  `json:"name"`
	Team           string  `json:"team"` // TeamA or TeamB
	Kills          int     `json:"kills"`
	Deaths         int     `json:"deaths"`
	Assists        int     `json:"assists"`
	Headshots      int     `json:"headshots"`
	DamageDealt    int     `json:"damage_dealt"`
	FlashAssists   int     `json:"flash_assists"`
	EntryKills     int     `json:"entry_kills"`
	EntryDeaths    int     `json:"entry_deaths"`
	TradeKills     int     `json:"trade_kills"`
	TradedDeaths   int     `json:"traded_deaths"`
	GrenadesThrown int     `json:"grenades_thrown"`
	EnemiesFlashed int     `json:"enemies_flashed"`
	TeamFlashes    int     `json:"team_flashes"`
	KAST           float64 `json:"kast"`
	ADR            float64 `json:"adr"`
	RoundsPlayed   int     `json:"rounds_played"`
}

type DemoOutput struct {
	MapName         string                        `json:"map_name"`
	MatchID         string                        `json:"match_id"`
	TickRate        float64                       `json:"tick_rate"`
	TotalRounds     int                           `json:"total_rounds"`
	CTScore         int                           `json:"ct_score"`
	TScore          int                           `json:"t_score"`
	TeamAScore      int                           `json:"team_a_score"` // team-stable scores
	TeamBScore      int                           `json:"team_b_score"`
	Kills           []KillEvent                   `json:"kills"`
	Damages         []DamageEvent                 `json:"damages"`
	Flashes         []FlashEvent                  `json:"flashes"`
	Grenades        []GrenadeEvent                `json:"grenades"`
	BombEvents      []BombEvent                   `json:"bomb_events"`
	Rounds          []RoundEvent                  `json:"rounds"`
	PlayerRounds    map[string][]PlayerRoundStats `json:"player_rounds"`
	PlayerSummaries []PlayerSummary               `json:"player_summaries"`
	PositionSamples []PlayerPositionSample        `json:"position_samples"`
}

func sideStr(side common.Team) string {
	switch side {
	case common.TeamCounterTerrorists:
		return "CT"
	case common.TeamTerrorists:
		return "T"
	default:
		return "SPEC"
	}
}

func hitRegister(hg events.HitGroup) string {
	switch hg {
	case events.HitGroupChest:
		return "Chest"
	case events.HitGroupHead:
		return "Head"
	case events.HitGroupStomach:
		return "Stomach"
	case events.HitGroupLeftArm, events.HitGroupLeftLeg:
		return "Left Body"
	case events.HitGroupRightLeg, events.HitGroupRightArm:
		return "Right Body"
	default:
		return "Miss"
	}
}

func vec3(p r3.Vector) Vec3 {
	return Vec3{X: float32(p.X), Y: float32(p.Y), Z: float32(p.Z)}
}

func dist2D(a, b Vec3) float64 {
	dx := float64(a.X - b.X)
	dy := float64(a.Y - b.Y)
	return math.Sqrt(dx*dx + dy*dy)
}

func safeParse(p dem.Parser) (err error) {
	defer func() {
		if r := recover(); r != nil {
			log.Printf("Recovered from panic: %v", r)
			err = fmt.Errorf("panic recovered: %v", r)
		}
	}()
	return p.ParseToEnd()
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: go run parser_file.go <demo.dem> [output.json]")
		os.Exit(1)
	}
	demoPath := os.Args[1]
	outPath := ""
	if len(os.Args) >= 3 {
		outPath = os.Args[2]
	}

	f, err := os.Open(demoPath)
	if err != nil {
		log.Fatalf("open demo: %v", err)
	}
	defer f.Close()

	cfg := dem.DefaultParserConfig
	cfg.MsgQueueBufferSize = -1
	cfg.IgnorePacketEntitiesPanic = true // silently skip broken entity packets (CS2 POV demo bug)
	p := dem.NewParserWithConfig(f, cfg)
	defer p.Close()
	fmt.Println("Parser created successfully")

	out := &DemoOutput{
		PlayerRounds: make(map[string][]PlayerRoundStats),
	}

	currentRound := 0
	roundStart := 0
	roundCTEquip := 0
	roundTEquip := 0

	type deathRecord struct {
		tick          int
		killerSteamID uint64
		victimSteamID uint64
		victimSide    string // side of the player who died
	}
	var roundDeaths []deathRecord
	var roundKills []KillEvent
	roundPlayerStats := make(map[uint64]*PlayerRoundStats)

	type dmgKey struct {
		steamID uint64
		round   int
	}
	playerRoundDamage := make(map[dmgKey]int)

	type kastKey struct {
		steamID uint64
		round   int
	}
	kastKill := make(map[kastKey]bool)
	kastAssist := make(map[kastKey]bool)
	kastSurvive := make(map[kastKey]bool)
	kastTraded := make(map[kastKey]bool)

	tickInterval := 32
	lastTick := 0

	// initialTeams: assigned once when we first see 10 players (not just round 1,
	// because some demos have empty participant lists on the very first RoundStart).
	// TeamA = started as CT, TeamB = started as T.
	initialTeams := map[uint64]string{}
	teamsInitialized := false

	tryInitTeams := func(gs dem.GameState) {
		if teamsInitialized {
			return
		}
		players := gs.Participants().Playing()
		if len(players) < 10 {
			return // wait until full lobby is visible
		}
		for _, pl := range players {
			if pl.Team == common.TeamCounterTerrorists {
				initialTeams[pl.SteamID64] = "TeamA"
			} else {
				initialTeams[pl.SteamID64] = "TeamB"
			}
		}
		teamsInitialized = true
	}

	p.RegisterEventHandler(func(e events.RoundStart) {
		fmt.Println("ROUND START")
		currentRound++
		roundStart = p.GameState().IngameTick()
		roundDeaths = nil
		roundKills = nil
		roundPlayerStats = make(map[uint64]*PlayerRoundStats)

		gs := p.GameState()
		tryInitTeams(gs)

		roundCTEquip = 0
		roundTEquip = 0
		for _, pl := range gs.Participants().Playing() {
			if pl.Team == common.TeamCounterTerrorists {
				roundCTEquip += pl.EquipmentValueCurrent()
			} else {
				roundTEquip += pl.EquipmentValueCurrent()
			}
			sid := pl.SteamID64
			roundPlayerStats[sid] = &PlayerRoundStats{
				Round:   currentRound,
				SteamID: sid,
				Name:    pl.Name,
				Side:    sideStr(pl.Team),
			}
		}
	})

	p.RegisterEventHandler(func(e events.RoundEnd) {
		endTick := p.GameState().IngameTick()
		gs := p.GameState()

		// also try here in case round 1 had an empty lobby
		tryInitTeams(gs)

		for _, pl := range gs.Participants().Playing() {
			if pl.IsAlive() {
				sid := pl.SteamID64
				kastSurvive[kastKey{sid, currentRound}] = true
				if s, ok := roundPlayerStats[sid]; ok {
					s.Survived = true
				}
			}
		}

		for sid, s := range roundPlayerStats {
			key := fmt.Sprintf("%d", sid)
			out.PlayerRounds[key] = append(out.PlayerRounds[key], *s)
		}

		winner := ""
		switch e.Winner {
		case common.TeamCounterTerrorists:
			winner = "CT"
			out.CTScore++
		case common.TeamTerrorists:
			winner = "T"
			out.TScore++
		}

		// team-stable score: figure out which team was CT this round
		if teamsInitialized {
			// pick any player from roundPlayerStats and check their initial team vs their current side
			for sid, s := range roundPlayerStats {
				initTeam := initialTeams[sid]
				if s.Side == "CT" {
					if initTeam == "TeamA" && winner == "CT" {
						out.TeamAScore++
					} else if initTeam == "TeamB" && winner == "CT" {
						out.TeamBScore++
					} else if initTeam == "TeamA" && winner == "T" {
						out.TeamBScore++
					} else if initTeam == "TeamB" && winner == "T" {
						out.TeamAScore++
					}
				}
				break // one player is enough to determine both team sides for the round
			}
		}

		out.Rounds = append(out.Rounds, RoundEvent{
			Round:        currentRound,
			StartTick:    roundStart,
			EndTick:      endTick,
			Winner:       winner,
			WinReason:    fmt.Sprint(e.Reason),
			Duration:     endTick - roundStart,
			CTEquipValue: roundCTEquip,
			TEquipValue:  roundTEquip,
		})
	})

	p.RegisterEventHandler(func(e events.Kill) {
		tick := p.GameState().IngameTick()
		if e.Killer == nil || e.Victim == nil {
			return
		}

		// Trade detection: the killer avenged a teammate death within the trade window.
		// A kill is a trade if: victim killed someone on the killer's team recently.
		tradeTicks := 320 // 5s @ 64Hz
		isTrade := false
		for _, d := range roundDeaths {
			sameTeamDied := d.victimSide == sideStr(e.Killer.Team)     // a teammate of killer died
			wasKilledByVictim := d.killerSteamID == e.Victim.SteamID64 // ...and our current victim killed them
			withinWindow := tick-d.tick <= tradeTicks
			if sameTeamDied && wasKilledByVictim && withinWindow {
				isTrade = true
				break
			}
		}

		isEntry := len(roundKills) == 0

		weapon := ""
		if e.Weapon != nil {
			weapon = e.Weapon.String()
		}

		ke := KillEvent{
			Tick:          tick,
			Round:         currentRound,
			KillerName:    e.Killer.Name,
			KillerSteamID: e.Killer.SteamID64,
			KillerSide:    sideStr(e.Killer.Team),
			KillerTeam:    initialTeams[e.Killer.SteamID64],
			VictimTeam:    initialTeams[e.Victim.SteamID64],
			VictimName:    e.Victim.Name,
			VictimSteamID: e.Victim.SteamID64,
			VictimSide:    sideStr(e.Victim.Team),
			Weapon:        weapon,
			Headshot:      e.IsHeadshot,
			Wallbang:      e.PenetratedObjects > 0,
			NoScope:       e.NoScope,
			ThroughSmoke:  e.ThroughSmoke,
			AttackerBlind: e.AttackerBlind,
			IsEntry:       isEntry,
			IsTrade:       isTrade,
			KillerPos:     vec3(e.Killer.Position()),
			VictimPos:     vec3(e.Victim.Position()),
		}
		out.Kills = append(out.Kills, ke)
		roundKills = append(roundKills, ke)

		roundDeaths = append(roundDeaths, deathRecord{
			tick:          tick,
			killerSteamID: e.Killer.SteamID64,
			victimSteamID: e.Victim.SteamID64,
			victimSide:    sideStr(e.Victim.Team),
		})

		ksid := e.Killer.SteamID64
		vsid := e.Victim.SteamID64
		if s, ok := roundPlayerStats[ksid]; ok {
			s.Kills++
			if e.IsHeadshot {
				s.Headshots++
			}
			if isEntry {
				s.EntryKill = true
				s.OpeningDuel = true
			}
			if isTrade {
				s.TradeKills++
			}
		}
		if s, ok := roundPlayerStats[vsid]; ok {
			s.Deaths++
			if isEntry {
				s.EntryDeath = true
				s.OpeningDuel = true
			}
			if isTrade {
				s.TradedDeath = true
				kastTraded[kastKey{vsid, currentRound}] = true
			}
		}

		if e.AssistedFlash && e.Assister != nil {
			asid := e.Assister.SteamID64
			if s, ok := roundPlayerStats[asid]; ok {
				s.FlashAssists++
			}
			kastAssist[kastKey{asid, currentRound}] = true
		} else if e.Assister != nil {
			asid := e.Assister.SteamID64
			if s, ok := roundPlayerStats[asid]; ok {
				s.Assists++
			}
			kastAssist[kastKey{asid, currentRound}] = true
		}

		kastKill[kastKey{ksid, currentRound}] = true
	})

	p.RegisterEventHandler(func(e events.PlayerHurt) {
		if e.Attacker == nil || e.Player == nil {
			return
		}
		weapon := ""
		if e.Weapon != nil {
			weapon = e.Weapon.String()
		}
		out.Damages = append(out.Damages, DamageEvent{
			Tick:            p.GameState().IngameTick(),
			Round:           currentRound,
			AttackerName:    e.Attacker.Name,
			AttackerSteamID: e.Attacker.SteamID64,
			VictimName:      e.Player.Name,
			Weapon:          weapon,
			HealthDamage:    e.HealthDamage,
			ArmorDamage:     e.ArmorDamage,
			HitGroup:        hitRegister(e.HitGroup),
		})
		if s, ok := roundPlayerStats[e.Attacker.SteamID64]; ok {
			s.DamageDealt += e.HealthDamage
		}
		playerRoundDamage[dmgKey{e.Attacker.SteamID64, currentRound}] += e.HealthDamage
	})

	p.RegisterEventHandler(func(e events.PlayerFlashed) {
		if e.Attacker == nil || e.Player == nil {
			return
		}
		out.Flashes = append(out.Flashes, FlashEvent{
			Tick:           p.GameState().IngameTick(),
			Round:          currentRound,
			ThrowerName:    e.Attacker.Name,
			ThrowerSteamID: e.Attacker.SteamID64,
			ThrowerSide:    sideStr(e.Attacker.Team),
			FlashedName:    e.Player.Name,
			FlashedSide:    sideStr(e.Player.Team),
			Duration:       float32(e.FlashDuration().Seconds()),
			IsTeamFlash:    e.Attacker.Team == e.Player.Team,
		})
	})

	p.RegisterEventHandler(func(e events.GrenadeProjectileDestroy) {
		if e.Projectile == nil || e.Projectile.Thrower == nil {
			return
		}
		out.Grenades = append(out.Grenades, GrenadeEvent{
			Tick:           p.GameState().IngameTick(),
			Round:          currentRound,
			ThrowerName:    e.Projectile.Thrower.Name,
			ThrowerSteamID: e.Projectile.Thrower.SteamID64,
			ThrowerSide:    sideStr(e.Projectile.Thrower.Team),
			GrenadeType:    e.Projectile.WeaponInstance.String(),
			Position:       vec3(e.Projectile.Position()),
		})
		if s, ok := roundPlayerStats[e.Projectile.Thrower.SteamID64]; ok {
			s.GrenadesThrown++
		}
	})

	p.RegisterEventHandler(func(e events.BombPlanted) {
		name := ""
		if e.Player != nil {
			name = e.Player.Name
		}

		site := "Unknown"

		switch e.Site {
		case events.BombsiteA:
			site = "A"
		case events.BombsiteB:
			site = "B"
		}

		out.BombEvents = append(out.BombEvents, BombEvent{
			Tick:       p.GameState().IngameTick(),
			Round:      currentRound,
			EventType:  "planted",
			PlayerName: name,
			Site:       site,
		})
	})
	p.RegisterEventHandler(func(e events.BombDefused) {
		name := ""
		if e.Player != nil {
			name = e.Player.Name
		}
		out.BombEvents = append(out.BombEvents, BombEvent{
			Tick: p.GameState().IngameTick(), Round: currentRound,
			EventType: "defused", PlayerName: name,
		})
	})
	p.RegisterEventHandler(func(e events.BombExplode) {
		out.BombEvents = append(out.BombEvents, BombEvent{
			Tick: p.GameState().IngameTick(), Round: currentRound,
			EventType: "exploded",
		})
	})

	// Map name via ConVars event
	p.RegisterEventHandler(func(e events.ConVarsUpdated) {
		if name, ok := e.UpdatedConVars["mapname"]; ok && name != "" {
			out.MapName = name
		}
	})

	// Position samples every N ticks
	p.RegisterEventHandler(func(e events.FrameDone) {
		tick := p.GameState().IngameTick()
		if tick-lastTick < tickInterval {
			return
		}
		lastTick = tick
		for _, pl := range p.GameState().Participants().Playing() {
			pos := pl.Position()
			out.PositionSamples = append(out.PositionSamples, PlayerPositionSample{
				Tick:    tick,
				Round:   currentRound,
				SteamID: pl.SteamID64,
				Name:    pl.Name,
				Pos:     Vec3{float32(pos.X), float32(pos.Y), float32(pos.Z)},
				IsAlive: pl.IsAlive(),
			})
		}
	})

	fmt.Println("Starting demo parse...")
	out.TickRate = p.TickRate()

	err = safeParse(p)
	if err != nil {
		log.Printf("parse completed with issues: %v", err)
	}

	out.TotalRounds = currentRound

	playerMap := make(map[uint64]*PlayerSummary)
	for _, k := range out.Kills {
		ps := getOrCreate(playerMap, k.KillerSteamID, k.KillerName, k.KillerTeam)
		ps.Kills++
		if k.Headshot {
			ps.Headshots++
		}
		if k.IsEntry {
			ps.EntryKills++
		}
		if k.IsTrade {
			ps.TradeKills++
		}
		pv := getOrCreate(playerMap, k.VictimSteamID, k.VictimName, k.VictimTeam)
		pv.Deaths++
		if k.IsEntry {
			pv.EntryDeaths++
		}
		if k.IsTrade {
			pv.TradedDeaths++
		}
	}
	for _, d := range out.Damages {
		ps := getOrCreate(playerMap, d.AttackerSteamID, d.AttackerName, "")
		ps.DamageDealt += d.HealthDamage
	}
	for _, fl := range out.Flashes {
		ps := getOrCreate(playerMap, fl.ThrowerSteamID, fl.ThrowerName, "")
		if fl.IsTeamFlash {
			ps.TeamFlashes++
		} else {
			ps.EnemiesFlashed++
		}
	}
	for _, g := range out.Grenades {
		ps := getOrCreate(playerMap, g.ThrowerSteamID, g.ThrowerName, "")
		ps.GrenadesThrown++
	}
	for _, rounds := range out.PlayerRounds {
		if len(rounds) > 0 {
			sid := rounds[0].SteamID
			ps := getOrCreate(playerMap, sid, rounds[0].Name, "")
			ps.RoundsPlayed = len(rounds)
		}
	}

	// fill Team from initialTeams for any player who only appears in damages/flashes/grenades
	for sid, ps := range playerMap {
		if ps.Team == "" {
			if t, ok := initialTeams[sid]; ok {
				ps.Team = t
			}
		}
	}

	for _, ps := range playerMap {
		sid := ps.SteamID
		kastCount := 0
		rounds := ps.RoundsPlayed
		if rounds == 0 {
			rounds = 1
		}
		for r := 1; r <= currentRound; r++ {
			k := kastKey{sid, r}
			if kastKill[k] || kastAssist[k] || kastSurvive[k] || kastTraded[k] {
				kastCount++
			}
		}
		ps.KAST = float64(kastCount) / float64(rounds)
		if rounds > 0 {
			ps.ADR = float64(ps.DamageDealt) / float64(rounds)
		}
	}

	for _, ps := range playerMap {
		out.PlayerSummaries = append(out.PlayerSummaries, *ps)
	}
	sort.Slice(out.PlayerSummaries, func(i, j int) bool {
		return out.PlayerSummaries[i].Kills > out.PlayerSummaries[j].Kills
	})

	data, err := json.MarshalIndent(out, "", "  ")
	if err != nil {
		log.Fatalf("marshal: %v", err)
	}
	if outPath != "" {
		if err := os.WriteFile(outPath, data, 0644); err != nil {
			log.Fatalf("write: %v", err)
		}
		fmt.Fprintf(os.Stderr, "wrote %d bytes to %s\n", len(data), outPath)
	} else {
		fmt.Println(string(data))
	}

	_ = dist2D
	_ = playerRoundDamage
}

func getOrCreate(m map[uint64]*PlayerSummary, sid uint64, name string, team string) *PlayerSummary {
	if ps, ok := m[sid]; ok {
		if ps.Team == "" && team != "" {
			ps.Team = team
		}
		return ps
	}
	ps := &PlayerSummary{SteamID: sid, Name: name, Team: team}
	m[sid] = ps
	return ps
}
